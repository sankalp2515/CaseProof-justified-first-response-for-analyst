# Protected remote state: versioned, uniform-access bucket owned by the project owner.
terraform {
  backend "gcs" {
    bucket = "caseproof-511713-tfstate"
    prefix = "runtime"
  }
}
