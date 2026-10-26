terraform {
  required_version = ">= 1.9, < 2.0"
  required_providers {
    google = { source = "hashicorp/google", version = "= 8.7.0" }
  }
}

variable "deployment_enabled" {
  type    = bool
  default = false
}
variable "frontend_backend_tests_passed" {
  type    = bool
  default = false
}
variable "dispatch_enabled" {
  type    = bool
  default = false
}
variable "project_id" {
  type    = string
  default = "caseproof-511713"
}
variable "project_number" {
  type    = string
  default = "273389900025"
}
variable "region" {
  type    = string
  default = "asia-south1"
}
variable "namespace" {
  type    = string
  default = "cloud-demo-v1"
}
variable "application_image" {
  type    = string
  default = "deployment-held.invalid/backend@sha256:0000000000000000000000000000000000000000000000000000000000000000"
  validation {
    condition     = can(regex("@sha256:[0-9a-f]{64}$", var.application_image))
    error_message = "Use an immutable tested application digest."
  }
}
variable "scanner_image" {
  type    = string
  default = "deployment-held.invalid/scanner@sha256:0000000000000000000000000000000000000000000000000000000000000000"
  validation {
    condition     = can(regex("@sha256:[0-9a-f]{64}$", var.scanner_image))
    error_message = "Use an immutable tested scanner digest."
  }
}
variable "frontend_image" {
  type    = string
  default = ""
  validation {
    condition     = var.frontend_image == "" || can(regex("@sha256:[0-9a-f]{64}$", var.frontend_image))
    error_message = "Use an immutable tested frontend digest."
  }
}
variable "public_domain" {
  type    = string
  default = "deployment-held.invalid"
}
variable "processor_id" {
  type    = string
  default = ""
}
variable "processor_version" {
  type    = string
  default = ""
}
variable "gemini_model" {
  type    = string
  default = "gemini-3.5-flash"
}
variable "staff_audience" {
  type    = string
  default = ""
}
variable "staff_principals" {
  type    = map(object({ role = string, tenant_id = string }))
  default = {}
}
variable "practice_personas" {
  description = "Synthetic demo: analyst/reviewer personas confined to each visitor's practice session, instead of Google staff sign-in"
  type        = bool
  default     = false
}
variable "alert_email" {
  type    = string
  default = ""
}

provider "google" {
  project = var.project_id
  region  = var.region
}

resource "terraform_data" "deployment_gate" {
  lifecycle {
    precondition {
      condition     = var.alert_email != "" && var.deployment_enabled && var.frontend_backend_tests_passed && var.frontend_image != "" && var.processor_version != "" && (var.practice_personas || (var.staff_audience != "" && length(var.staff_principals) > 0)) && !endswith(var.public_domain, ".invalid") && !startswith(var.application_image, "deployment-held") && !startswith(var.scanner_image, "deployment-held")
      error_message = "DEPLOYMENT HELD: frontend/backend acceptance, real image digests, processor/version, staff identity mapping or practice personas, and domain are required. Do not enable without the user's deployment instruction."
    }
  }
}
variable "practice_daily_limit" {
  description = "Practice sessions per UTC day across all visitors"
  type        = number
  default     = 200
}
variable "llm_daily_call_cap" {
  description = "Gemini calls per UTC day across all visitors (a cost guard)"
  type        = number
  default     = 3000
}
