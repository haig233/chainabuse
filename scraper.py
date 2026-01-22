# ============================================
# CHAINABUSE SCRAPER
# Works in both Google Colab and GitHub Actions
# Features: Incremental Google Drive uploads every 50 URLs
# ============================================

# ============================================
# ENVIRONMENT DETECTION & SETUP
# ============================================
import os

IS_COLAB = 'COLAB_GPU' in os.environ

if IS_COLAB:
    print("🔧 Running in Google Colab")
    from google.colab import drive
    drive.mount('/content/drive')
    from tqdm.notebook import tqdm
    output_dir = '/content/drive/MyDrive/CryptForensic/chainabuse_scraper-02/'
else:
    print("🔧 Running in GitHub Actions / Local")
    from tqdm import tqdm
    output_dir = './output/'

# Create output directory
os.makedirs(output_dir, exist_ok=True)
print(f"✅ Output directory: {output_dir}")

# ============================================
# IMPORTS
# ============================================
import asyncio
from playwright.async_api import async_playwright
import json
import time
import pandas as pd
from datetime import datetime
import random
import base64

# Google Drive imports
try:
    from googleapiclient.discovery import build
    from google.oauth2 import service_account
    from googleapiclient.http import MediaFileUpload
    DRIVE_AVAILABLE = True
    print("✅ Google Drive libraries loaded")
except ImportError:
    DRIVE_AVAILABLE = False
    print("⚠️  Google Drive libraries not installed")

# ============================================
# GOOGLE DRIVE UPLOAD FUNCTION
# ============================================

def upload_to_drive_incremental(file_path, folder_id=None):
    """Upload single file to Google Drive incrementally"""
    if not DRIVE_AVAILABLE:
        print("  ⚠️  Google Drive libraries not available")
        return False
    
    try:
        creds_base64 = os.getenv('GOOGLE_DRIVE_CREDENTIALS')
        folder_id = folder_id or os.getenv('DRIVE_FOLDER_ID')
        
        if not creds_base64 or not folder_id:
            print("  ⚠️  Credentials or Folder ID missing")
            return False
        
        creds_json = base64.b64decode(creds_base64).decode('utf-8')
        creds_dict = json.loads(creds_json)
        
        credentials = service_account.Credentials.from_service_account_info(
            creds_dict,
            scopes=['https://www.googleapis.com/auth/drive.file']
        )
        
        service = build('drive', 'v3', credentials=credentials)
        
        file_metadata = {
            'name': os.path.basename(file_path),
            'parents': [folder_id]
        }
        
        media = MediaFileUpload(file_path, resumable=True)
        
        file = service.files().create(
            body=file_metadata,
            media_body=media,
            fields='id,name',
            supportsAllDrives=True  # ← Critical for shared folders
        ).execute()
        
        print(f"  ☁️  Uploaded: {file.get('name')} (ID: {file.get('id')})")
        return True
        
    except Exception as e:
        error_msg = str(e)
        if 'storageQuotaExceeded' in error_msg:
            print("  ❌ Folder not properly shared with service account!")
            print("     1. Share folder with service account email")
            print("     2. Give 'Editor' permission")
            print("     3. Make sure folder ID is correct")
        else:
            print(f"  ❌ Upload failed: {error_msg[:200]}")
        return False

# ============================================
# CORE SCRAPING FUNCTIONS
# ============================================

async def scrape_url(browser, url, semaphore, retry_count=0):
    """Scrape single URL with rate limiting and retry"""
    async with semaphore:
        # Smart sleep
        if retry_count > 0:
            await asyncio.sleep(random.uniform(2, 5))
        else:
            await asyncio.sleep(random.uniform(0.3, 0.8))
        
        context = None
        page = None
        
        try:
            context = await browser.new_context(
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                viewport={'width': 1920, 'height': 1080}
            )
            page = await context.new_page()
            
            # Set extra headers
            await page.set_extra_http_headers({
                'Accept-Language': 'en-US,en;q=0.9',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8'
            })
            
            await page.goto(url, wait_until='networkidle', timeout=30000)
            await asyncio.sleep(5)
            
            # Check if selector exists
            card_count = await page.evaluate('''() => {
                return document.querySelectorAll('.create-ScamReportCard').length;
            }''')
            
            if card_count == 0:
                await asyncio.sleep(3)
                card_count = await page.evaluate('''() => {
                    return document.querySelectorAll('.create-ScamReportCard').length;
                }''')
            
            if card_count == 0:
                return {
                    'url': url,
                    'reports': [],
                    'success': True,
                    'empty': True,
                    'note': 'No reports found',
                    'retry_count': retry_count
                }
            
            # Extract reports
            reports = await page.evaluate(r'''() => {
                const cards = document.querySelectorAll('.create-ScamReportCard');
                
                return Array.from(cards).map(card => {
                    const category = card.querySelector('.create-ScamReportCard__category-label')?.textContent?.trim();
                    const description = card.querySelector('.create-ScamReportCard__preview-description')?.textContent?.trim();
                    
                    const submittedInfo = card.querySelector('.create-ScamReportCard__submitted-info');
                    let submittedBy = null;
                    let submittedTime = null;
                    
                    if (submittedInfo) {
                        const linkEl = submittedInfo.querySelector('.create-Link__label');
                        const textEls = submittedInfo.querySelectorAll('.create-Text');
                        
                        if (linkEl) {
                            submittedBy = linkEl.textContent?.trim();
                        } else if (textEls[0]?.textContent?.includes('in')) {
                            submittedBy = textEls[0].textContent.replace('Submitted in', '').trim();
                        }
                        
                        const lastText = Array.from(textEls).pop();
                        if (lastText) {
                            submittedTime = lastText.textContent.replace('on ', '').trim();
                        }
                    }
                    
                    const voteCount = card.querySelector('.create-BidirectionalVoting__vote-count')?.textContent?.trim();
                    
                    const addressSections = card.querySelectorAll('.create-ReportedSection__address-section');
                    const addresses = [];
                    const domains = [];
                    
                    addressSections.forEach(section => {
                        const addressText = section.querySelector('.create-ResponsiveAddress__text')?.textContent?.trim();
                        const domainText = section.querySelector('.create-ReportedSection__domain')?.textContent?.trim();
                        const chainImg = section.querySelector('img[alt]');
                        const blockchain = chainImg?.alt?.replace(' logo', '') || null;
                        const badge = section.querySelector('.create-Badge span')?.textContent?.trim();
                        
                        if (addressText) {
                            addresses.push({ 
                                address: addressText, 
                                blockchain: blockchain,
                                tag: badge || null
                            });
                        }
                        
                        if (domainText) {
                            domains.push(domainText);
                        }
                    });
                    
                    return {
                        category: category,
                        description: description,
                        submitted_by: submittedBy,
                        submitted_time: submittedTime,
                        vote_count: parseInt(voteCount) || 0,
                        addresses: addresses,
                        domains: domains,
                        total_addresses: addresses.length,
                        total_domains: domains.length
                    };
                });
            }''')
            
            # Add source URL and metadata
            for report in reports:
                report['source_url'] = url
                report['scraped_at'] = datetime.now().isoformat()
            
            return {
                'url': url,
                'reports': reports,
                'success': True,
                'empty': len(reports) == 0,
                'report_count': len(reports),
                'retry_count': retry_count
            }
        
        except Exception as e:
            error_msg = str(e)
            
            if 'Timeout' in error_msg or 'timeout' in error_msg:
                error_type = 'Timeout'
            elif 'TargetClosed' in error_msg or 'closed' in error_msg:
                error_type = 'Browser Closed'
            elif 'net::ERR' in error_msg:
                error_type = 'Network Error'
            elif '404' in error_msg:
                error_type = '404 Not Found'
            elif '429' in error_msg or 'Too Many Requests' in error_msg:
                error_type = '429 Rate Limit'
            else:
                error_type = 'Unknown Error'
            
            return {
                'url': url,
                'error': error_msg[:200],
                'error_type': error_type,
                'success': False,
                'retry_count': retry_count
            }
        
        finally:
            try:
                if page and not page.is_closed():
                    await page.close()
            except:
                pass
            try:
                if context:
                    await context.close()
            except:
                pass


async def scrape_batch(urls, max_concurrent=5, retry_count=0):
    """Process batch of URLs with progress bar"""
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=[
                '--no-sandbox',
                '--disable-setuid-sandbox',
                '--disable-dev-shm-usage',
                '--disable-blink-features=AutomationControlled'
            ]
        )
        semaphore = asyncio.Semaphore(max_concurrent)
        
        tasks = [scrape_url(browser, url, semaphore, retry_count) for url in urls]
        results = []
        
        desc = "Retrying" if retry_count > 0 else "Scraping"
        for coro in tqdm(asyncio.as_completed(tasks), total=len(urls), desc=desc):
            result = await coro
            results.append(result)
        
        await browser.close()
        return results


def save_batch_file(batch_num, url_start, url_end, urls_data, batch_dir):
    """Save batch of 50 URLs with all their data"""
    
    # Categorize URLs
    successful_urls = []
    empty_urls = []
    failed_urls = []
    
    for data in urls_data:
        if not data['success']:
            failed_urls.append({
                'url': data['url'],
                'error_type': data.get('error_type', 'Unknown'),
                'error': data.get('error', ''),
                'retry_count': data.get('retry_count', 0)
            })
        elif data.get('empty', False):
            empty_urls.append({
                'url': data['url'],
                'note': 'No reports found'
            })
        else:
            successful_urls.append({
                'url': data['url'],
                'reports': data['reports'],
                'total_reports': len(data['reports']),
                'total_addresses': sum(len(r.get('addresses', [])) for r in data['reports']),
                'total_domains': sum(len(r.get('domains', [])) for r in data['reports'])
            })
    
    # Create batch data
    batch_data = {
        'batch_number': batch_num,
        'url_range': {
            'start': url_start,
            'end': url_end,
            'total': url_end - url_start
        },
        'created_at': datetime.now().isoformat(),
        'summary': {
            'total_urls': len(urls_data),
            'successful': len(successful_urls),
            'empty': len(empty_urls),
            'failed': len(failed_urls),
            'total_reports': sum(u['total_reports'] for u in successful_urls),
            'total_addresses': sum(u['total_addresses'] for u in successful_urls),
            'total_domains': sum(u['total_domains'] for u in successful_urls)
        },
        'successful_urls': successful_urls,
        'empty_urls': empty_urls,
        'failed_urls': failed_urls
    }
    
    # Save JSON
    batch_file = f'{batch_dir}batch-{batch_num}.json'
    if os.path.exists(batch_file):
        os.remove(batch_file)
    
    with open(batch_file, 'w') as f:
        json.dump(batch_data, f, indent=2)
    
    print(f"💾 Saved batch-{batch_num}.json (URLs {url_start}-{url_end}: ✅{len(successful_urls)} 📭{len(empty_urls)} ❌{len(failed_urls)})")
    
    # Upload to Drive immediately after each batch
    upload_to_drive_incremental(batch_file)
    
    return batch_file


def save_checkpoint(all_reports, processed, failed_urls, total_urls, stats, permanently_failed=None):
    """Save checkpoint"""
    checkpoint_data = {
        'reports': all_reports,
        'processed': processed,
        'failed': failed_urls,
        'permanently_failed': permanently_failed or [],
        'total_urls': total_urls,
        'stats': stats,
        'timestamp': datetime.now().isoformat()
    }
    
    checkpoint_file = f'{output_dir}checkpoint_{processed}.json'
    if os.path.exists(checkpoint_file):
        os.remove(checkpoint_file)
    
    with open(checkpoint_file, 'w') as f:
        json.dump(checkpoint_data, f, indent=2)
    
    # Upload checkpoint to Drive
    upload_to_drive_incremental(checkpoint_file)
    
    return checkpoint_file


def load_latest_checkpoint():
    """Load latest checkpoint"""
    try:
        checkpoints = [int(f.split('.')[0].split('_')[-1]) 
                      for f in os.listdir(output_dir) 
                      if f.startswith('checkpoint_') and f.endswith('.json')]
        
        if not checkpoints:
            return None
        
        latest_num = sorted(checkpoints)[-1]
        latest = f'checkpoint_{latest_num}.json'
        checkpoint_path = os.path.join(output_dir, latest)
        
        print(f"📂 Found checkpoint: {latest}")
        with open(checkpoint_path, 'r') as f:
            return json.load(f)
    except Exception as e:
        print(f"⚠️  Error: {e}")
        return None


def flatten_reports(reports):
    """Flatten reports for CSV"""
    csv_data = []
    for report in reports:
        base = {
            'source_url': report.get('source_url', ''),
            'scraped_at': report.get('scraped_at', ''),
            'category': report.get('category'),
            'description': report.get('description'),
            'submitted_by': report.get('submitted_by'),
            'submitted_time': report.get('submitted_time'),
            'vote_count': report.get('vote_count'),
        }
        
        if report.get('addresses'):
            for addr in report['addresses']:
                row = base.copy()
                row.update({
                    'address': addr.get('address'),
                    'blockchain': addr.get('blockchain'),
                    'tag': addr.get('tag'),
                    'domain': ', '.join(report.get('domains', []))
                })
                csv_data.append(row)
        elif report.get('domains'):
            for domain in report['domains']:
                row = base.copy()
                row.update({'address': '', 'blockchain': '', 'tag': '', 'domain': domain})
                csv_data.append(row)
        else:
            row = base.copy()
            row.update({'address': '', 'blockchain': '', 'tag': '', 'domain': ''})
            csv_data.append(row)
    
    return csv_data


async def scrape_all_colab(all_urls, batch_size=50, max_concurrent=5, checkpoint_interval=250, max_retries=2):
    """Scrape with batch saving every 50 URLs"""
    all_reports = []
    failed_urls = []
    permanently_failed = []
    start_index = 0
    
    # Create batch directory
    batch_dir = f'{output_dir}url_batches/'
    os.makedirs(batch_dir, exist_ok=True)
    
    # Stats
    stats = {
        'total_processed': 0,
        'successful_urls': 0,
        'failed_urls': 0,
        'empty_pages': 0,
        'pages_with_reports': 0,
        'total_reports': 0,
        'total_addresses': 0,
        'total_domains': 0,
        'total_batches_saved': 0,
        'errors_by_type': {},
        'avg_reports_per_page': 0,
        'start_time': datetime.now().isoformat(),
        'last_update': datetime.now().isoformat()
    }
    
    # Load checkpoint
    checkpoint = load_latest_checkpoint()
    if checkpoint:
        all_reports = checkpoint.get('reports', [])
        start_index = checkpoint.get('processed', 0)
        failed_urls = checkpoint.get('failed', [])
        permanently_failed = checkpoint.get('permanently_failed', [])
        stats = checkpoint.get('stats', stats)
        
        print(f"✅ Resuming from URL {start_index}")
        print(f"📦 Batches saved: {stats.get('total_batches_saved', 0)}")
    
    urls_to_process = all_urls[start_index:]
    total_batches = (len(urls_to_process) + batch_size - 1) // batch_size
    
    try:
        for i in range(0, len(urls_to_process), batch_size):
            batch_num = (start_index + i) // batch_size + 1
            batch_urls = urls_to_process[i:i+batch_size]
            current_index = start_index + i
            
            print(f"\n{'='*70}")
            print(f"📦 Batch {batch_num} | URLs: {current_index}-{current_index+len(batch_urls)-1}")
            print(f"{'='*70}")
            
            batch_start_time = time.time()
            batch_results_data = []
            
            try:
                results = await scrape_batch(batch_urls, max_concurrent=max_concurrent)
                
                batch_stats = {'successful': 0, 'failed': 0, 'empty': 0, 'with_reports': 0, 'reports': 0}
                batch_failed = []
                
                for result in results:
                    stats['total_processed'] += 1
                    batch_results_data.append(result)
                    
                    if result['success']:
                        stats['successful_urls'] += 1
                        batch_stats['successful'] += 1
                        
                        if result.get('empty', False):
                            stats['empty_pages'] += 1
                            batch_stats['empty'] += 1
                        else:
                            stats['pages_with_reports'] += 1
                            batch_stats['with_reports'] += 1
                            batch_stats['reports'] += len(result['reports'])
                            all_reports.extend(result['reports'])
                            stats['total_reports'] = len(all_reports)
                    else:
                        stats['failed_urls'] += 1
                        batch_stats['failed'] += 1
                        batch_failed.append(result)
                        
                        error_type = result.get('error_type', 'Unknown')
                        stats['errors_by_type'][error_type] = stats['errors_by_type'].get(error_type, 0) + 1
                
                stats['total_addresses'] = sum(len(r.get('addresses', [])) for r in all_reports)
                stats['total_domains'] = sum(len(r.get('domains', [])) for r in all_reports)
                stats['avg_reports_per_page'] = stats['total_reports'] / max(stats['pages_with_reports'], 1)
                stats['last_update'] = datetime.now().isoformat()
                
                batch_time = time.time() - batch_start_time
                print(f"\n📊 ✅{batch_stats['successful']} ❌{batch_stats['failed']} 📭{batch_stats['empty']} 📝{batch_stats['reports']} | ⚡{len(batch_urls)/batch_time:.1f}/s")
                
                # Retry failed
                if batch_failed:
                    print(f"\n🔄 Retrying {len(batch_failed)}...")
                    for retry_attempt in range(1, max_retries + 1):
                        if not batch_failed:
                            break
                        await asyncio.sleep(5)
                        retry_urls = [r['url'] for r in batch_failed]
                        retry_results = await scrape_batch(retry_urls, max_concurrent=3, retry_count=retry_attempt)
                        still_failed = []
                        
                        for result in retry_results:
                            # Update batch_results_data with retry results
                            for idx, orig in enumerate(batch_results_data):
                                if orig['url'] == result['url']:
                                    batch_results_data[idx] = result
                                    break
                            
                            if result['success']:
                                all_reports.extend(result['reports'])
                                stats['total_reports'] = len(all_reports)
                                print(f"  ✅ Recovered: {result['url']}")
                            else:
                                still_failed.append(result)
                        
                        batch_failed = still_failed
                    
                    for failed_result in batch_failed:
                        permanently_failed.append({
                            'url': failed_result['url'],
                            'error': failed_result.get('error', ''),
                            'error_type': failed_result.get('error_type', 'Unknown'),
                            'retries': max_retries,
                            'failed_at': datetime.now().isoformat()
                        })
                
                # Save batch file (uploads to Drive automatically)
                save_batch_file(
                    batch_num, 
                    current_index, 
                    current_index + len(batch_urls),
                    batch_results_data,
                    batch_dir
                )
                stats['total_batches_saved'] = batch_num
                
                # Save checkpoint (uploads to Drive automatically)
                if (current_index + batch_size) % checkpoint_interval == 0 or (i + batch_size) >= len(urls_to_process):
                    save_checkpoint(all_reports, current_index + batch_size, failed_urls, len(all_urls), stats, permanently_failed)
                    print(f"\n💾 Checkpoint saved | Batches: {stats['total_batches_saved']}")
            
            except Exception as e:
                print(f"\n❌ Error: {e}")
                save_checkpoint(all_reports, current_index, failed_urls, len(all_urls), stats, permanently_failed)
            
            await asyncio.sleep(2)
    
    except KeyboardInterrupt:
        print(f"\n⚠️  Interrupted!")
        save_checkpoint(all_reports, start_index + i, failed_urls, len(all_urls), stats, permanently_failed)
        raise
    
    return all_reports, permanently_failed, stats, batch_dir


# ============================================
# MAIN EXECUTION
# ============================================

async def main():
    """Main function"""
    
    # Test Google Drive upload first
    print("\n" + "="*70)
    print("🧪 TESTING GOOGLE DRIVE CONNECTION")
    print("="*70)
    
    test_file = f'{output_dir}test_upload.txt'
    with open(test_file, 'w') as f:
        f.write(f"Test upload at {datetime.now()}\n")
        f.write(f"Environment: {'Colab' if IS_COLAB else 'GitHub Actions'}\n")
    
    if upload_to_drive_incremental(test_file):
        print("✅ Google Drive upload test PASSED - Check your Drive folder!\n")
    else:
        print("❌ Google Drive upload test FAILED - Check errors above\n")
    
    print("="*70)
    print("🚀 STARTING SCRAPER")
    print("="*70 + "\n")
    
    # Read CSV
    df = pd.read_csv('sitemap-0.csv')
    urls_list = df['loc'].tolist()
    urls_list = [url for url in urls_list if '/address/' in url]
    
    print(f"📋 Total URLs: {len(urls_list)}")
    urls_list = urls_list[20000:]  # Limit to 10,000
    
    start_time = time.time()
    
    try:
        all_reports, permanently_failed, stats, batch_dir = await scrape_all_colab(
            all_urls=urls_list,
            batch_size=50,
            max_concurrent=5,
            checkpoint_interval=250,
            max_retries=2
        )
        
        elapsed = time.time() - start_time
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        
        # Save final results
        final_json = f'{output_dir}final_reports_{timestamp}.json'
        with open(final_json, 'w') as f:
            json.dump(all_reports, f, indent=2)
        upload_to_drive_incremental(final_json)
        
        csv_data = flatten_reports(all_reports)
        final_csv = f'{output_dir}final_reports_{timestamp}.csv'
        pd.DataFrame(csv_data).to_csv(final_csv, index=False)
        upload_to_drive_incremental(final_csv)
        
        if permanently_failed:
            failed_csv = f'{output_dir}permanently_failed_{timestamp}.csv'
            pd.DataFrame(permanently_failed).to_csv(failed_csv, index=False)
            upload_to_drive_incremental(failed_csv)
        
        stats['end_time'] = datetime.now().isoformat()
        stats['total_elapsed_seconds'] = elapsed
        stats['urls_per_hour'] = len(urls_list) / (elapsed / 3600)
        
        stats_file = f'{output_dir}final_stats_{timestamp}.json'
        with open(stats_file, 'w') as f:
            json.dump(stats, f, indent=2)
        upload_to_drive_incremental(stats_file)
        
        print(f"\n{'='*70}")
        print(f"✅ COMPLETE")
        print(f"{'='*70}")
        print(f"📊 Reports: {len(all_reports)}")
        print(f"🔗 Addresses: {stats['total_addresses']}")
        print(f"📦 URL batches saved: {stats['total_batches_saved']}")
        print(f"✅ Successful: {stats['successful_urls']} | ❌ Failed: {len(permanently_failed)}")
        print(f"⏱️  {elapsed/60:.2f} min | {stats['urls_per_hour']:.1f} URLs/hr")
        print(f"\n📁 {batch_dir}")
        print(f"🎉 Done!")
    
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
