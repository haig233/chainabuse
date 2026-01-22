# chainabuse

# ChainAbuse Scraper

Automated scraper for ChainAbuse.com with incremental Google Drive uploads.

## Features

- ✅ Runs every 6 hours automatically
- ✅ Uploads each batch (50 URLs) to Google Drive immediately
- ✅ Uploads checkpoints every 250 URLs
- ✅ Checkpoint/resume support
- ✅ Works in both Colab and GitHub Actions

## Schedule

Runs automatically at:
- 00:00 UTC (5:30 AM IST)
- 06:00 UTC (11:30 AM IST)
- 12:00 UTC (5:30 PM IST)
- 18:00 UTC (11:30 PM IST)

## Setup

### 1. Create Google Service Account

1. Go to [Google Cloud Console](https://console.cloud.google.com)
2. Create new project
3. Enable **Google Drive API**
4. Create **Service Account**
5. Download JSON key

### 2. Setup Google Drive

1. Create folder in Google Drive
2. Share with service account email
3. Copy folder ID from URL

### 3. Add GitHub Secrets

```bash
# Encode credentials
cat service-account-key.json | base64
