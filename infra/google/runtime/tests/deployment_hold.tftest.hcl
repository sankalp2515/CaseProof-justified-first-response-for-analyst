# Native provider mocks: no Google credentials, requests or resource changes.
mock_provider "google" {}

# Existing queue adoption is tested as an overridden import; Terraform does not
# support importing from mock providers themselves.
override_resource {
  target = google_cloud_tasks_queue.processing
  values = { id = "projects/caseproof-511713/locations/asia-south1/queues/caseproof-processing" }
}

override_resource {
  target = google_compute_global_address.edge
  values = { id = "projects/caseproof-511713/global/addresses/caseproof-edge", address = "192.0.2.10" }
}

run "default_configuration_cannot_deploy" {
  command         = plan
  expect_failures = [terraform_data.deployment_gate]
}

run "reviewable_plan_keeps_dispatch_paused" {
  command = plan
  variables {
    deployment_enabled            = true
    frontend_backend_tests_passed = true
    application_image             = "asia-south1-docker.pkg.dev/example-project/caseproof/backend@sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
    scanner_image                 = "asia-south1-docker.pkg.dev/example-project/caseproof/scanner@sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
    frontend_image                = "asia-south1-docker.pkg.dev/example-project/caseproof/frontend@sha256:cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc"
    processor_id                  = "offline-processor"
    processor_version             = "offline-version"
    staff_audience                = "offline-client.apps.googleusercontent.com"
    staff_principals              = { offline_staff = { role = "analyst", tenant_id = "demo" } }
    alert_email                   = "operator@example.invalid"
    public_domain                 = "demo.example.com"
  }
  assert {
    condition     = google_cloud_tasks_queue.processing.desired_state == "PAUSED" && google_cloud_scheduler_job.reconcile.paused
    error_message = "A reviewed deployment must not implicitly enable dispatch."
  }
  assert {
    condition     = google_cloud_run_v2_service.backend["api"].ingress == "INGRESS_TRAFFIC_INTERNAL_LOAD_BALANCER" && google_cloud_run_v2_service.frontend[0].ingress == "INGRESS_TRAFFIC_INTERNAL_LOAD_BALANCER"
    error_message = "Public API/frontend must not bypass the Armor load balancer."
  }
  assert {
    condition     = google_cloud_tasks_queue.processing.rate_limits[0].max_concurrent_dispatches <= 5 && google_cloud_run_v2_service.backend["worker"].template[0].scaling[0].max_instance_count <= 5
    error_message = "Prototype worker and task concurrency must remain bounded."
  }
  assert {
    condition     = alltrue([for binding in google_cloud_run_v2_service_iam_member.worker_invokers : binding.member != "allUsers"]) && google_cloud_run_v2_service_iam_member.scanner.member != "allUsers" && google_cloud_run_v2_service_iam_member.simulator.member != "allUsers"
    error_message = "Worker, scanner and simulator must remain IAM-private."
  }
  assert {
    condition     = google_storage_bucket.quarantine.public_access_prevention == "enforced" && google_storage_bucket.quarantine.uniform_bucket_level_access
    error_message = "Evidence quarantine must not allow public objects."
  }
  assert {
    condition     = !google_compute_backend_service.api.log_config[0].enable
    error_message = "Raw load-balancer request URLs must not retain customer bearer tokens."
  }
}

run "practice_personas_replace_staff_identity_for_the_synthetic_demo" {
  command = plan
  variables {
    deployment_enabled            = true
    frontend_backend_tests_passed = true
    practice_personas             = true
    application_image             = "asia-south1-docker.pkg.dev/example-project/caseproof/backend@sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
    scanner_image                 = "asia-south1-docker.pkg.dev/example-project/caseproof/scanner@sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
    frontend_image                = "asia-south1-docker.pkg.dev/example-project/caseproof/frontend@sha256:cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc"
    processor_id                  = "offline-processor"
    processor_version             = "offline-version"
    alert_email                   = "operator@example.invalid"
    public_domain                 = "demo.example.com"
  }
  assert {
    condition     = google_cloud_run_v2_service.backend["api"].ingress == "INGRESS_TRAFFIC_INTERNAL_LOAD_BALANCER"
    error_message = "The API must only be reachable through the load balancer."
  }
  assert {
    condition     = google_cloud_tasks_queue.processing.desired_state == "PAUSED"
    error_message = "Dispatch stays paused until explicitly enabled."
  }
}
