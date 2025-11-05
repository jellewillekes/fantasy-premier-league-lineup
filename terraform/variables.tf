variable "project_id" {
  description = "GCP project ID used for all resources."
  type        = string
}

variable "region" {
  description = "Default compute region."
  type        = string
  default     = "europe-west4"
}

variable "location" {
  description = "Default location for storage/BigQuery (e.g. EU multi-region)."
  type        = string
  default     = "EU"
}
