resource "google_logging_metric" "backend_errors" {
  name   = "caseproof/backend_errors"
  filter = "resource.type=\"cloud_run_revision\" AND resource.labels.service_name=~\"caseproof-.*\" AND severity>=ERROR AND jsonPayload.event:*"
  metric_descriptor {
    metric_kind = "DELTA"
    value_type  = "INT64"
  }
  depends_on = [terraform_data.deployment_gate]
}
resource "google_logging_metric" "request_latency" {
  name            = "caseproof/request_latency_ms"
  filter          = "resource.type=\"cloud_run_revision\" AND jsonPayload.event=\"http_request\""
  value_extractor = "EXTRACT(jsonPayload.latency_ms)"
  metric_descriptor {
    metric_kind = "DELTA"
    value_type  = "DISTRIBUTION"
    unit        = "ms"
  }
  bucket_options {
    exponential_buckets {
      num_finite_buckets = 20
      growth_factor      = 2
      scale              = 1
    }
  }
  depends_on = [terraform_data.deployment_gate]
}
resource "google_monitoring_notification_channel" "operator" {
  count        = var.alert_email == "" ? 0 : 1
  display_name = "CaseProof operator"
  type         = "email"
  labels       = { email_address = var.alert_email }
  depends_on   = [terraform_data.deployment_gate]
}
resource "google_monitoring_alert_policy" "backend_errors" {
  display_name          = "CaseProof backend errors"
  combiner              = "OR"
  notification_channels = var.alert_email == "" ? [] : [google_monitoring_notification_channel.operator[0].name]
  conditions {
    display_name = "Backend errors in five minutes"
    condition_threshold {
      filter = "resource.type=\"cloud_run_revision\" AND metric.type=\"logging.googleapis.com/user/${google_logging_metric.backend_errors.name}\""
      # Single retried failures (a Document AI timeout, a Gemini 429) recover on
      # their own; alert only on a sustained burst.
      duration        = "0s"
      comparison      = "COMPARISON_GT"
      threshold_value = 3
      aggregations {
        alignment_period   = "300s"
        per_series_aligner = "ALIGN_SUM"
      }
    }
  }
}
resource "google_monitoring_alert_policy" "queue_backlog" {
  display_name          = "CaseProof queue backlog"
  combiner              = "OR"
  notification_channels = var.alert_email == "" ? [] : [google_monitoring_notification_channel.operator[0].name]
  conditions {
    display_name = "More than five queued commands for two minutes"
    condition_threshold {
      filter          = "resource.type=\"cloud_tasks_queue\" AND resource.labels.queue_id=\"caseproof-processing\" AND metric.type=\"cloudtasks.googleapis.com/queue/depth\""
      duration        = "120s"
      comparison      = "COMPARISON_GT"
      threshold_value = 5
      aggregations {
        alignment_period   = "60s"
        per_series_aligner = "ALIGN_MAX"
      }
    }
  }
  depends_on = [terraform_data.deployment_gate]
}

resource "google_service_account" "build" {
  account_id = "caseproof-build"
  depends_on = [terraform_data.deployment_gate]
}
resource "google_storage_bucket" "build_source" {
  name                        = "${var.project_id}-build-source"
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
resource "google_storage_bucket_iam_member" "build_source" {
  bucket = google_storage_bucket.build_source.name
  role   = "roles/storage.objectViewer"
  member = "serviceAccount:${google_service_account.build.email}"
}
resource "google_artifact_registry_repository_iam_member" "build_images" {
  location   = var.region
  repository = "caseproof"
  role       = "roles/artifactregistry.writer"
  member     = "serviceAccount:${google_service_account.build.email}"
}
resource "google_project_iam_member" "build_logs" {
  project = var.project_id
  role    = "roles/logging.logWriter"
  member  = "serviceAccount:${google_service_account.build.email}"
}

# Existing evidence bucket, default Firestore database, BigQuery dataset, registry
# and project billing controls remain owned by scripts/cloud_foundation.py.
# No authoritative project IAM policy, destructive migration or budget replacement.

resource "google_logging_metric" "queue_age" {
  name            = "caseproof/queue_age_ms"
  filter          = "resource.type=\"cloud_run_revision\" AND jsonPayload.event=\"job_attempt\""
  value_extractor = "EXTRACT(jsonPayload.queue_age_ms)"
  metric_descriptor {
    metric_kind = "DELTA"
    value_type  = "DISTRIBUTION"
    unit        = "ms"
  }
  bucket_options {
    exponential_buckets {
      num_finite_buckets = 20
      growth_factor      = 2
      scale              = 1
    }
  }
  depends_on = [terraform_data.deployment_gate]
}
resource "google_monitoring_alert_policy" "queue_age" {
  display_name          = "CaseProof processing queue delay"
  combiner              = "OR"
  notification_channels = var.alert_email == "" ? [] : [google_monitoring_notification_channel.operator[0].name]
  conditions {
    display_name = "Observed queue delay exceeds one minute"
    condition_threshold {
      filter          = "resource.type=\"cloud_run_revision\" AND metric.type=\"logging.googleapis.com/user/${google_logging_metric.queue_age.name}\""
      duration        = "60s"
      comparison      = "COMPARISON_GT"
      threshold_value = 60000
      aggregations {
        alignment_period   = "60s"
        per_series_aligner = "ALIGN_PERCENTILE_99"
      }
    }
  }
}

resource "google_firestore_field" "unindexed_payloads" {
  for_each = {
    revisions = "data", approvals = "data", model_cache = "result",
    outbox    = "payload", bank_publications = "payload", synthetic_networks = "data"
  }
  project    = var.project_id
  database   = "(default)"
  collection = each.key
  field      = each.value
  index_config {}
  depends_on = [terraform_data.deployment_gate]
}

# Platform request URLs can contain bearer upload-link tokens. Retain the
# application's route-template-only request events instead of raw URL logs.
resource "google_logging_project_exclusion" "raw_request_urls" {
  name        = "caseproof-sensitive-request-urls"
  description = "Do not retain platform URLs containing customer capability tokens"
  filter      = "resource.type=\"cloud_run_revision\" AND resource.labels.service_name=~\"caseproof-.*\" AND log_id(\"run.googleapis.com/requests\")"
  depends_on  = [terraform_data.deployment_gate]
}
