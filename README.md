# ChainAbuse Scraper - GitHub Actions

Automated scraper for ChainAbuse data that runs on GitHub Actions and saves results directly to the repository.

## Features

- ✅ Runs automatically on GitHub Actions
- 💾 Saves data directly to repository after every 50 URLs
- 🔄 Automatic git commits and pushes
- 📊 Checkpoint recovery system
- 🔁 Retry mechanism for failed URLs
- 📦 Batch processing with progress tracking

## Setup Instructions

### 1. Create Repository Structure

```
your-repo/
├── .github/
│   └── workflows/
│       └── scraper.yml
├── chainabuse_scraper_github.py
├── requirements.txt
├── sitemap-0.csv
├── .gitignore
└── README.md
```

### 2. Upload Files

1. Create a new GitHub repository
2. Upload all the files to your repository:
   - `chainabuse_scraper_github.py` (main scraper script)
   - `.github/workflows/scraper.yml` (GitHub Actions workflow)
   - `requirements.txt` (Python dependencies)
   - `sitemap-0.csv` (your URL list)
   - `.gitignore`
   - `README.md`

### 3. Configure Repository Settings

1. Go to **Settings** → **Actions** → **General**
2. Under "Workflow permissions", select:
   - ✅ **Read and write permissions**
   - ✅ **Allow GitHub Actions to create and approve pull requests**
3. Click **Save**

### 4. Run the Scraper

#### Option A: Manual Trigger
1. Go to **Actions** tab
2. Click on "ChainAbuse Scraper" workflow
3. Click **Run workflow**
4. (Optional) Set start/end index
5. Click **Run workflow**

#### Option B: Scheduled Run
- The workflow runs automatically every 6 hours (configured in `scraper.yml`)
- Modify the cron schedule if needed

## Output Structure

```
chainabuse_data/
├── url_batches/
│   ├── batch-1.json       (URLs 0-49)
│   ├── batch-2.json       (URLs 50-99)
│   ├── batch-3.json       (URLs 100-149)
│   └── ...
├── checkpoint_500.json
├── checkpoint_1000.json
├── final_reports_YYYYMMDD_HHMMSS.json
├── final_reports_YYYYMMDD_HHMMSS.csv
├── permanently_failed_YYYYMMDD_HHMMSS.csv
└── final_stats_YYYYMMDD_HHMMSS.json
```

## How It Works

1. **Scrapes 50 URLs** at a time
2. **Saves batch file** with all data
3. **Commits and pushes** to GitHub immediately
4. **Creates checkpoints** every 500 URLs
5. **Retries failed URLs** up to 2 times
6. **Resumes from checkpoint** if interrupted

## Batch File Format

Each `batch-X.json` contains:
- URL range information
- Summary statistics
- Successful URLs with all their reports
- Empty URLs (no reports found)
- Failed URLs with error details

## Monitoring Progress

1. Check **Actions** tab for live logs
2. Browse `chainabuse_data/url_batches/` folder for results
3. View commit history for progress updates

## Important Notes

### GitHub Actions Limits
- ⏱️ **6 hour timeout** per workflow run
- 💾 **Repository size limit**: Keep total data under 5GB
- 🔄 **Concurrent runs**: One workflow at a time

### Adjusting Settings

Edit `chainabuse_scraper_github.py`:
```python
await scrape_all_github(
    all_urls=urls_list,
    batch_size=50,          # URLs per batch file
    max_concurrent=10,      # Parallel requests
    checkpoint_interval=500,# Checkpoint frequency
    max_retries=2          # Retry attempts
)
```

Edit `.github/workflows/scraper.yml`:
```yaml
schedule:
  - cron: '0 */6 * * *'  # Every 6 hours
timeout-minutes: 360     # 6 hour max runtime
```

## Troubleshooting

### Workflow Not Running
- Check repository permissions (Settings → Actions)
- Ensure workflow file is in `.github/workflows/`
- Check workflow syntax (Actions tab shows errors)

### Git Push Failures
- Verify write permissions are enabled
- Check for repository size limits
- Ensure no merge conflicts

### High Memory Usage
- Reduce `max_concurrent` from 10 to 5
- Reduce `batch_size` from 50 to 25
- Increase sleep times

### Resume from Checkpoint
- The scraper automatically detects and loads the latest checkpoint
- Deletes old checkpoint files to save space
- Continue from where it left off

## Data Analysis

After scraping completes, analyze the data:

```python
import json
import pandas as pd

# Load final reports
with open('chainabuse_data/final_reports_YYYYMMDD_HHMMSS.json') as f:
    reports = json.load(f)

# Or load CSV
df = pd.read_csv('chainabuse_data/final_reports_YYYYMMDD_HHMMSS.csv')
print(df.head())
```

## License

MIT License - Feel free to modify and use as needed.
