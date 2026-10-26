# Standard Cloud Armor only. This does not enroll in Enterprise or inspect file malware.
resource "google_compute_security_policy" "uploads" {
  name = "caseproof-upload-edge"
  advanced_options_config {
    log_level = "NORMAL"
  }
  rule {
    action   = "throttle"
    priority = 100
    match {
      # Cloud Armor regular expressions reject capture groups; use prefixes.
      expr { expression = "request.method == 'POST' && (request.path.startsWith('/v1/victim/') || request.path.startsWith('/v1/customer/'))" }
    }
    rate_limit_options {
      conform_action = "allow"
      exceed_action  = "deny(429)"
      enforce_on_key = "IP"
      rate_limit_threshold {
        count        = 30
        interval_sec = 60
      }
    }
    description = "Bound public victim commands per source IP; application limits remain mandatory"
  }
  rule {
    action   = "deny(403)"
    priority = 200
    preview  = true
    match {
      expr { expression = "evaluatePreconfiguredWaf('sqli-v33-stable', {'sensitivity': 1}) || evaluatePreconfiguredWaf('xss-v33-stable', {'sensitivity': 1})" }
    }
    description = "Preview WAF first; enable blocking only after representative multipart and complaint tests"
  }
  rule {
    action   = "allow"
    priority = 2147483647
    match {
      versioned_expr = "SRC_IPS_V1"
      config { src_ip_ranges = ["*"] }
    }
  }
  depends_on = [terraform_data.deployment_gate, google_project_service.runtime_apis]
}

resource "google_compute_region_network_endpoint_group" "api" {
  name                  = "caseproof-api-neg"
  network_endpoint_type = "SERVERLESS"
  region                = var.region
  cloud_run { service = google_cloud_run_v2_service.backend["api"].name }
}
resource "google_compute_backend_service" "api" {
  name                  = "caseproof-api-edge"
  protocol              = "HTTP"
  load_balancing_scheme = "EXTERNAL_MANAGED"
  security_policy       = google_compute_security_policy.uploads.id
  backend { group = google_compute_region_network_endpoint_group.api.id }
  log_config {
    enable      = false
    sample_rate = 0
  }
}

resource "google_cloud_run_v2_service" "frontend" {
  count               = var.frontend_image == "" ? 0 : 1
  name                = "caseproof-frontend"
  location            = var.region
  ingress             = "INGRESS_TRAFFIC_INTERNAL_LOAD_BALANCER"
  deletion_protection = true
  template {
    service_account = google_service_account.runtime["frontend"].email
    scaling {
      min_instance_count = 0
      max_instance_count = 2
    }
    containers {
      image = var.frontend_image
      resources {
        limits   = { cpu = "1", memory = "256Mi" }
        cpu_idle = true
      }
    }
  }
  depends_on = [terraform_data.deployment_gate]
}
resource "google_cloud_run_v2_service_iam_member" "frontend" {
  count    = var.frontend_image == "" ? 0 : 1
  name     = google_cloud_run_v2_service.frontend[0].name
  location = var.region
  role     = "roles/run.invoker"
  member   = "allUsers"
}
resource "google_compute_region_network_endpoint_group" "frontend" {
  count                 = var.frontend_image == "" ? 0 : 1
  name                  = "caseproof-frontend-neg"
  network_endpoint_type = "SERVERLESS"
  region                = var.region
  cloud_run { service = google_cloud_run_v2_service.frontend[0].name }
}
resource "google_compute_backend_service" "frontend" {
  count                 = var.frontend_image == "" ? 0 : 1
  name                  = "caseproof-frontend-edge"
  protocol              = "HTTP"
  load_balancing_scheme = "EXTERNAL_MANAGED"
  security_policy       = google_compute_security_policy.uploads.id
  backend { group = google_compute_region_network_endpoint_group.frontend[0].id }
}
resource "google_compute_url_map" "edge" {
  name            = "caseproof-edge"
  default_service = var.frontend_image == "" ? google_compute_backend_service.api.id : google_compute_backend_service.frontend[0].id
  host_rule {
    hosts        = [var.public_domain]
    path_matcher = "caseproof"
  }
  path_matcher {
    name            = "caseproof"
    default_service = var.frontend_image == "" ? google_compute_backend_service.api.id : google_compute_backend_service.frontend[0].id
    path_rule {
      paths   = ["/v1/*", "/health"]
      service = google_compute_backend_service.api.id
    }
  }
}
resource "google_compute_managed_ssl_certificate" "edge" {
  name = "caseproof-edge-tls"
  managed { domains = [var.public_domain] }
  depends_on = [terraform_data.deployment_gate]
}
resource "google_compute_ssl_policy" "edge" {
  name            = "caseproof-tls"
  profile         = "MODERN"
  min_tls_version = "TLS_1_2"
  depends_on      = [terraform_data.deployment_gate]
}
resource "google_compute_target_https_proxy" "edge" {
  name             = "caseproof-edge"
  url_map          = google_compute_url_map.edge.id
  ssl_certificates = [google_compute_managed_ssl_certificate.edge.id]
  ssl_policy       = google_compute_ssl_policy.edge.id
}
# Reserved before the first apply so the public domain (sslip.io) can name its IP.
import {
  to = google_compute_global_address.edge
  id = "projects/${var.project_id}/global/addresses/caseproof-edge"
}
resource "google_compute_global_address" "edge" {
  name       = "caseproof-edge"
  depends_on = [terraform_data.deployment_gate]
}
resource "google_compute_global_forwarding_rule" "https" {
  name                  = "caseproof-https"
  target                = google_compute_target_https_proxy.edge.id
  ip_address            = google_compute_global_address.edge.address
  port_range            = "443"
  load_balancing_scheme = "EXTERNAL_MANAGED"
}

output "edge_ip" { value = google_compute_global_address.edge.address }
output "worker_origin" { value = local.worker_origin }
