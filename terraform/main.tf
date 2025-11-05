locals {
  project_id = var.project_id
  region     = var.region
  location   = var.location

  environment    = "dev"
  project_prefix = "fpl"
}

# BigQuery dataset: fpl
resource "google_bigquery_dataset" "fpl" {
  dataset_id = "fpl"
  project    = local.project_id
  location   = local.location

  friendly_name = "Fantasy Premier League"
  description   = "Core dataset for FPL EP modeling and optimization."

  labels = {
    env       = local.environment
    component = "fpl-engine"
  }
}

# Simple raw table for testing ingestion
resource "google_bigquery_table" "players_raw" {
  project   = local.project_id
  dataset_id = google_bigquery_dataset.fpl.dataset_id
  table_id   = "players_raw"

  deletion_protection = false

  schema = jsonencode([
    {
      name        = "ingest_timestamp"
      type        = "TIMESTAMP"
      mode        = "REQUIRED"
      description = "Ingestion time of the record."
    },
    {
      name        = "player_id"
      type        = "INT64"
      mode        = "REQUIRED"
      description = "Unique ID of the player from FPL."
    },
    {
      name        = "raw_json"
      type        = "STRING"
      mode        = "REQUIRED"
      description = "Raw JSON payload for the player as received from the API."
    }
  ])

  labels = {
    env       = local.environment
    component = "ingestion"
  }
}
