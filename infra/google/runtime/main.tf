locals {
  worker_origin     = "https://caseproof-worker-${var.project_number}.${var.region}.run.app"
  simulator_origin  = "https://caseproof-simulator-${var.project_number}.${var.region}.run.app"
  scanner_origin    = "https://caseproof-scanner-${var.project_number}.${var.region}.run.app"
  evidence_bucket   = "${var.project_id}-evidence-mumbai"
  quarantine_bucket = "${var.project_id}-quarantine-mumbai"
  processor_id      = var.processor_id != "" ? var.processor_id : reverse(split("/", google_document_ai_processor.evidence[0].name))[0]
  common_env = {
    RUNTIME_BACKEND              = "google", APP_ENVIRONMENT = "demo", DEMO_MODE = "true",
    DATA_DIR                     = "/tmp/caseproof", LLM_PROVIDER = "vertex", LLM_MODE = "live",
    ALLOW_FALLBACK               = "false", EXTERNAL_WORKER = "true", CUSTOMER_PORTAL = "true",
    GOOGLE_CLOUD_PROJECT         = var.project_id, GOOGLE_CLOUD_LOCATION = var.region,
    GEMINI_MODEL                 = var.gemini_model, OCR_PROVIDER = "documentai",
    DOCUMENTAI_LOCATION          = var.region, DOCUMENTAI_PROCESSOR_ID = local.processor_id,
    DOCUMENTAI_PROCESSOR_VERSION = var.processor_version, FIRESTORE_NAMESPACE = var.namespace,
    STORAGE_BACKEND              = "gcs", GCS_BUCKET = local.evidence_bucket,
    GCS_QUARANTINE_BUCKET        = local.quarantine_bucket, BIGQUERY_DATASET = "caseproof_bank",
    BIGQUERY_MAXIMUM_BYTES       = "100000000", CLOUD_TASKS_QUEUE = "caseproof-processing",
    CLOUD_WORKER_URL             = local.worker_origin, CLOUD_SIMULATOR_URL = local.simulator_origin,
    CLOUD_SCANNER_URL            = local.scanner_origin,
    CLOUD_TASKS_ACCOUNT          = google_service_account.tasks.email,
    CLOUD_SCHEDULER_ACCOUNT      = google_service_account.scheduler.email,
    CLOUD_STAFF_AUDIENCE         = var.staff_audience,
    CLOUD_STAFF_PRINCIPALS       = jsonencode(var.staff_principals),
    CLOUD_PRACTICE_PERSONAS      = tostring(var.practice_personas),
    CLOUD_PRACTICE_DAILY_LIMIT   = tostring(var.practice_daily_limit),
    PUBLIC_BASE_URL              = "https://${var.public_domain}",
    LLM_MAX_CALLS_PER_CASE       = "24", LLM_DAILY_CALL_CAP = tostring(var.llm_daily_call_cap), LLM_MAX_OUTPUT_TOKENS = "4096",
    JOB_LEASE_SECONDS            = "90"
  }
}

resource "google_project_service" "runtime_apis" {
  for_each = toset(["run.googleapis.com", "documentai.googleapis.com", "cloudtasks.googleapis.com",
    "cloudscheduler.googleapis.com", "compute.googleapis.com", "monitoring.googleapis.com",
  "logging.googleapis.com", "cloudbuild.googleapis.com"])
  service            = each.value
  disable_on_destroy = false
  depends_on         = [terraform_data.deployment_gate]
}

resource "google_document_ai_processor" "evidence" {
  count        = var.processor_id == "" ? 1 : 0
  display_name = "CaseProof evidence OCR"
  type         = "OCR_PROCESSOR"
  location     = var.region
  lifecycle { prevent_destroy = true }
  depends_on = [google_project_service.runtime_apis]
}

resource "google_service_account" "runtime" {
  for_each     = toset(["api", "worker", "simulator", "scanner", "frontend"])
  account_id   = "caseproof-${each.key}"
  display_name = "CaseProof ${each.key}; no service account keys"
  depends_on   = [terraform_data.deployment_gate]
}
resource "google_service_account" "tasks" {
  account_id = "caseproof-tasks"
  depends_on = [terraform_data.deployment_gate]
}
resource "google_service_account" "scheduler" {
  account_id = "caseproof-scheduler"
  depends_on = [terraform_data.deployment_gate]
}

resource "google_storage_bucket" "quarantine" {
  name                        = local.quarantine_bucket
  location                    = var.region
  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"
  force_destroy               = false
  lifecycle_rule {
    condition { age = 7 }
    action { type = "Delete" }
  }
  lifecycle { prevent_destroy = true }
  depends_on = [terraform_data.deployment_gate]
}

resource "google_project_iam_member" "firestore" {
  for_each = toset(["api", "worker", "simulator"])
  project  = var.project_id
  role     = "roles/datastore.user"
  member   = "serviceAccount:${google_service_account.runtime[each.key].email}"
}
resource "google_project_iam_member" "worker_vertex" {
  project = var.project_id
  role    = "roles/aiplatform.user"
  member  = "serviceAccount:${google_service_account.runtime["worker"].email}"
}
# The API serves the on-demand Gemini summary, evidence reading and intake helper.
resource "google_project_iam_member" "api_vertex" {
  project = var.project_id
  role    = "roles/aiplatform.user"
  member  = "serviceAccount:${google_service_account.runtime["api"].email}"
}
resource "google_project_iam_member" "worker_ocr" {
  project = var.project_id
  role    = "roles/documentai.apiUser"
  member  = "serviceAccount:${google_service_account.runtime["worker"].email}"
}
resource "google_project_iam_member" "bq_jobs" {
  for_each = toset(["api", "worker"])
  project  = var.project_id
  role     = "roles/bigquery.jobUser"
  member   = "serviceAccount:${google_service_account.runtime[each.key].email}"
}
resource "google_bigquery_dataset_iam_member" "bank_read" {
  project    = var.project_id
  dataset_id = "caseproof_bank"
  role       = "roles/bigquery.dataViewer"
  member     = "serviceAccount:${google_service_account.runtime["api"].email}"
}
resource "google_bigquery_dataset_iam_member" "bank_write" {
  project    = var.project_id
  dataset_id = "caseproof_bank"
  role       = "roles/bigquery.dataEditor"
  member     = "serviceAccount:${google_service_account.runtime["worker"].email}"
}
# The API publishes a new practice session's synthetic bank batches directly so a
# judge does not wait behind complaint processing in the shared queue.
resource "google_bigquery_dataset_iam_member" "bank_write_api" {
  project    = var.project_id
  dataset_id = "caseproof_bank"
  role       = "roles/bigquery.dataEditor"
  member     = "serviceAccount:${google_service_account.runtime["api"].email}"
}
resource "google_storage_bucket_iam_member" "evidence" {
  for_each = { for pair in setproduct(["api", "worker"], ["roles/storage.objectCreator", "roles/storage.objectViewer"]) : "${pair[0]}-${pair[1]}" => pair }
  bucket   = local.evidence_bucket
  role     = each.value[1]
  member   = "serviceAccount:${google_service_account.runtime[each.value[0]].email}"
}
resource "google_storage_bucket_iam_member" "quarantine" {
  for_each = { for pair in setproduct(["api", "worker"], ["roles/storage.objectCreator", "roles/storage.objectViewer"]) : "${pair[0]}-${pair[1]}" => pair }
  bucket   = google_storage_bucket.quarantine.name
  role     = each.value[1]
  member   = "serviceAccount:${google_service_account.runtime[each.value[0]].email}"
}

resource "google_cloud_run_v2_service" "backend" {
  for_each            = toset(["api", "worker", "simulator"])
  name                = "caseproof-${each.key}"
  location            = var.region
  ingress             = each.key == "api" ? "INGRESS_TRAFFIC_INTERNAL_LOAD_BALANCER" : "INGRESS_TRAFFIC_ALL"
  deletion_protection = true
  template {
    service_account                  = google_service_account.runtime[each.key].email
    timeout                          = "240s"
    max_instance_request_concurrency = each.key == "worker" ? 1 : 8
    scaling {
      # API and worker stay warm: a cold start added ~30 s to a judge's first session.
      min_instance_count = contains(["api", "worker"], each.key) ? 1 : 0
      max_instance_count = each.key == "simulator" ? 1 : each.key == "worker" ? 5 : 2
    }
    containers {
      image   = var.application_image
      command = ["python", "-m", "uvicorn", "caseproof.cloud.entrypoint:app", "--host", "0.0.0.0", "--port", "8080", "--no-access-log"]
      resources {
        limits   = { cpu = "1", memory = "512Mi" }
        cpu_idle = true
      }
      dynamic "env" {
        for_each = merge(local.common_env, { CLOUD_COMPONENT = each.key })
        content {
          name  = env.key
          value = env.value
        }
      }
    }
  }
  depends_on = [google_project_service.runtime_apis]
}

resource "google_cloud_run_v2_service" "scanner" {
  name                = "caseproof-scanner"
  location            = var.region
  ingress             = "INGRESS_TRAFFIC_ALL"
  deletion_protection = true
  template {
    service_account = google_service_account.runtime["scanner"].email
    # One resident clamd engine serves up to its four scan threads.
    max_instance_request_concurrency = 4
    timeout                          = "160s"
    scaling {
      # Kept warm: a cold clamd loads its signatures for ~45 s before the first scan.
      min_instance_count = 1
      max_instance_count = 1
    }
    containers {
      image = var.scanner_image
      resources {
        limits            = { cpu = "1", memory = "2Gi" }
        cpu_idle          = true
        startup_cpu_boost = true
      }
      # Signature refresh (<=60s) plus one-time engine load (32-55s measured at 1 CPU).
      startup_probe {
        initial_delay_seconds = 10
        period_seconds        = 10
        failure_threshold     = 24
        http_get {
          path = "/health"
          port = 8080
        }
      }
    }
  }
  depends_on = [google_project_service.runtime_apis]
}

resource "google_cloud_run_v2_service_iam_member" "api_edge" {
  name     = google_cloud_run_v2_service.backend["api"].name
  location = var.region
  role     = "roles/run.invoker"
  member   = "allUsers"
}
resource "google_cloud_run_v2_service_iam_member" "worker_invokers" {
  for_each = { tasks = google_service_account.tasks.email, scheduler = google_service_account.scheduler.email }
  name     = google_cloud_run_v2_service.backend["worker"].name
  location = var.region
  role     = "roles/run.invoker"
  member   = "serviceAccount:${each.value}"
}
resource "google_cloud_run_v2_service_iam_member" "simulator" {
  name     = google_cloud_run_v2_service.backend["simulator"].name
  location = var.region
  role     = "roles/run.invoker"
  member   = "serviceAccount:${google_service_account.runtime["worker"].email}"
}
resource "google_cloud_run_v2_service_iam_member" "scanner" {
  name     = google_cloud_run_v2_service.scanner.name
  location = var.region
  role     = "roles/run.invoker"
  member   = "serviceAccount:${google_service_account.runtime["worker"].email}"
}

import {
  to = google_cloud_tasks_queue.processing
  id = "projects/${var.project_id}/locations/${var.region}/queues/caseproof-processing"
}
resource "google_cloud_tasks_queue" "processing" {
  name          = "caseproof-processing"
  location      = var.region
  desired_state = var.dispatch_enabled ? "RUNNING" : "PAUSED"
  # Parallel lanes so practice-bank publications never queue ahead of a complaint;
  # jobs stay safe through per-case leases and revision fencing.
  rate_limits {
    max_dispatches_per_second = 5
    max_concurrent_dispatches = 5
  }
  retry_config {
    # Six attempts over ~12 minutes: outlasts transient Vertex 429s (MAX_JOB_ATTEMPTS).
    max_attempts       = 6
    min_backoff        = "20s"
    max_backoff        = "300s"
    max_retry_duration = "1800s"
  }
  stackdriver_logging_config { sampling_ratio = 1 }
  lifecycle { prevent_destroy = true }
  depends_on = [terraform_data.deployment_gate, google_project_service.runtime_apis]
}
resource "google_cloud_tasks_queue_iam_member" "publishers" {
  for_each = toset(["api", "worker"])
  name     = google_cloud_tasks_queue.processing.name
  location = var.region
  role     = "roles/cloudtasks.enqueuer"
  member   = "serviceAccount:${google_service_account.runtime[each.key].email}"
}
resource "google_cloud_tasks_queue_iam_member" "viewers" {
  for_each = toset(["api", "worker"])
  name     = google_cloud_tasks_queue.processing.name
  location = var.region
  role     = "roles/cloudtasks.viewer"
  member   = "serviceAccount:${google_service_account.runtime[each.key].email}"
}
resource "google_service_account_iam_member" "task_act_as" {
  for_each           = toset(["api", "worker"])
  service_account_id = google_service_account.tasks.name
  role               = "roles/iam.serviceAccountUser"
  member             = "serviceAccount:${google_service_account.runtime[each.key].email}"
}
resource "google_cloud_scheduler_job" "reconcile" {
  name             = "caseproof-reconcile"
  region           = var.region
  schedule         = "* * * * *"
  time_zone        = "Etc/UTC"
  paused           = !var.dispatch_enabled
  attempt_deadline = "180s"
  retry_config { retry_count = 1 }
  http_target {
    uri         = "${local.worker_origin}/internal/reconcile"
    http_method = "POST"
    oidc_token {
      service_account_email = google_service_account.scheduler.email
      audience              = local.worker_origin
    }
  }
  depends_on = [google_project_service.runtime_apis, google_cloud_run_v2_service_iam_member.worker_invokers]
}

resource "google_bigquery_table" "records" {
  for_each            = toset(["bank_batches", "downstream_reports", "complaints"])
  project             = var.project_id
  dataset_id          = "caseproof_bank"
  table_id            = each.key
  deletion_protection = true
  clustering          = ["tenant", "id"]
  schema = jsonencode(concat([
    { name = "tenant", type = "STRING", mode = "REQUIRED" },
    { name = "id", type = "STRING", mode = "REQUIRED" },
    { name = "digest", type = "STRING", mode = "REQUIRED" },
    { name = "payload", type = "STRING", mode = "REQUIRED" },
    { name = "received_at", type = "TIMESTAMP", mode = "REQUIRED" }
  ], each.key == "downstream_reports" ? [{ name = "reported_at", type = "TIMESTAMP", mode = "REQUIRED" }] : []))
  depends_on = [terraform_data.deployment_gate]
}
