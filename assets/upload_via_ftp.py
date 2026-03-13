#!/usr/bin/env python3
"""
Daily Report PDF Uploader via FTP

Uploads PDFs directly to WordPress via FTP (bypassing ModSecurity).
This script:
1. Uploads PDFs to WordPress via FTP
2. Generates manifest.json
3. Uploads manifest via FTP
4. Cleans up old files (45+ days)
"""

import os
import sys
from pathlib import Path
from datetime import datetime
import logging
from dotenv import load_dotenv
from typing import Dict

# Import our custom modules
from ftp_uploader import FTPUploader
from manifest_generator import ManifestGenerator
from cleanup_old_files import FileCleanup
from email_notifier import EmailNotifier

# Configure logging
LOG_DIR = Path(__file__).parent.parent / "logs"
LOG_DIR.mkdir(exist_ok=True)
LOG_FILE = LOG_DIR / f"upload_{datetime.now().strftime('%Y%m%d')}.log"

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)


def main():
    """Main execution function."""
    logger.info("=" * 60)
    logger.info("Starting Daily Report Upload via FTP")
    logger.info("=" * 60)

    # Load environment variables
    env_path = Path(__file__).parent.parent / '.env'
    load_dotenv(env_path)

    # Get configuration from environment
    WP_SITE_URL = os.getenv('WP_SITE_URL', 'https://www.sheriff.douglas.ga.us')
    FTP_HOST = os.getenv('FTP_HOST')
    FTP_USERNAME = os.getenv('FTP_USERNAME')
    FTP_PASSWORD = os.getenv('FTP_PASSWORD')
    FTP_PORT = int(os.getenv('FTP_PORT', '21'))
    FTP_UPLOAD_PATH = os.getenv('FTP_UPLOAD_PATH', '/public_html/wp-content/uploads')
    USE_FTP_TLS = os.getenv('USE_FTP_TLS', 'true').lower() == 'true'
    PDF_DIRECTORY = Path(os.getenv('PDF_DIRECTORY', '/Users/tjjaglinski/Downloads/--DailyReports'))
    RETENTION_DAYS = int(os.getenv('RETENTION_DAYS', '45'))

    # Email configuration
    EMAIL_ENABLED = os.getenv('EMAIL_ENABLED', 'false').lower() == 'true'
    EMAIL_SMTP_SERVER = os.getenv('EMAIL_SMTP_SERVER', 'smtp.gmail.com')
    EMAIL_SMTP_PORT = int(os.getenv('EMAIL_SMTP_PORT', '587'))
    EMAIL_USERNAME = os.getenv('EMAIL_USERNAME')
    EMAIL_PASSWORD = os.getenv('EMAIL_PASSWORD')
    EMAIL_FROM = os.getenv('EMAIL_FROM')
    EMAIL_TO = os.getenv('EMAIL_TO')

    # Validate configuration
    if not all([FTP_HOST, FTP_USERNAME, FTP_PASSWORD]):
        logger.error("❌ Missing required FTP environment variables")
        logger.error("Please ensure .env file contains:")
        logger.error("  - FTP_HOST")
        logger.error("  - FTP_USERNAME")
        logger.error("  - FTP_PASSWORD")
        sys.exit(1)

    if not PDF_DIRECTORY.exists():
        logger.error(f"❌ PDF directory does not exist: {PDF_DIRECTORY}")
        sys.exit(1)

    logger.info(f"Configuration:")
    logger.info(f"  WordPress URL: {WP_SITE_URL}")
    logger.info(f"  FTP Host: {FTP_HOST}:{FTP_PORT}")
    logger.info(f"  FTP User: {FTP_USERNAME}")
    logger.info(f"  FTP TLS: {USE_FTP_TLS}")
    logger.info(f"  Upload Path: {FTP_UPLOAD_PATH}")
    logger.info(f"  PDF Directory: {PDF_DIRECTORY}")
    logger.info(f"  Retention Days: {RETENTION_DAYS}")
    logger.info("")

    try:
        # Initialize FTP uploader
        ftp = FTPUploader(FTP_HOST, FTP_USERNAME, FTP_PASSWORD, FTP_PORT, USE_FTP_TLS)

        # Connect to FTP
        if not ftp.connect():
            logger.error("❌ Failed to connect to FTP. Check credentials.")
            sys.exit(1)

        # Initialize manifest generator
        manifest_gen = ManifestGenerator(retention_days=RETENTION_DAYS)

        # Load existing URL mapping (filename -> WordPress URL)
        mapping_file = Path(__file__).parent.parent / 'url_mapping.json'
        url_mapping = manifest_gen.load_url_mapping(mapping_file)

        # Find PDFs to upload
        pdf_files = list(PDF_DIRECTORY.glob('*.pdf')) + list(PDF_DIRECTORY.glob('*.PDF'))
        logger.info(f"Found {len(pdf_files)} PDF file(s)")

        # Track statistics and errors
        stats = {
            'total': len(pdf_files),
            'uploaded': 0,
            'skipped': 0,
            'failed': 0
        }
        error_messages = []

        # Upload PDFs
        for pdf_file in pdf_files:
            # Check if already uploaded
            if pdf_file.name in url_mapping:
                logger.info(f"⏭️  Skipping {pdf_file.name} - already uploaded")
                stats['skipped'] += 1
                continue

            # Parse date for path structure
            metadata = manifest_gen.parse_filename(pdf_file.name)
            if not metadata:
                error_msg = f"Could not parse filename: {pdf_file.name}"
                logger.warning(f"⚠️  Skipping {pdf_file.name} - could not parse filename")
                error_messages.append(error_msg)
                stats['failed'] += 1
                continue

            # Extract year/month for path
            date_obj = datetime.strptime(metadata['date'], '%Y-%m-%d')
            year = date_obj.strftime('%Y')
            month = date_obj.strftime('%m')

            # Build remote path: /public_html/wp-content/uploads/daily-reports/2025/12/filename.pdf
            remote_path = f"{FTP_UPLOAD_PATH}/daily-reports/{year}/{month}/{pdf_file.name}"

            # Upload to FTP
            if ftp.upload_file(pdf_file, remote_path):
                # Generate URL
                file_url = ftp.get_file_url(remote_path, WP_SITE_URL)

                # Save URL mapping
                url_mapping[pdf_file.name] = file_url
                stats['uploaded'] += 1

                # Move to uploaded directory
                uploaded_dir = PDF_DIRECTORY / 'uploaded'
                uploaded_dir.mkdir(exist_ok=True)
                try:
                    destination = uploaded_dir / pdf_file.name
                    pdf_file.rename(destination)
                    logger.info(f"📁 Moved {pdf_file.name} to uploaded/")
                except Exception as e:
                    error_msg = f"Could not move file {pdf_file.name}: {str(e)}"
                    logger.warning(error_msg)
                    error_messages.append(error_msg)
            else:
                error_msg = f"Failed to upload: {pdf_file.name}"
                error_messages.append(error_msg)
                stats['failed'] += 1

        # Save URL mapping
        manifest_gen.save_url_mapping(url_mapping, mapping_file)

        # Generate manifest
        logger.info("")
        logger.info("=" * 60)
        logger.info("Generating manifest.json")
        logger.info("=" * 60)

        base_url = WP_SITE_URL
        manifest = manifest_gen.generate_manifest(
            pdf_directory=PDF_DIRECTORY / 'uploaded',
            base_url=base_url,
            url_mapping=url_mapping
        )

        # Save manifest locally
        manifest_path = Path(__file__).parent.parent / 'manifest.json'
        manifest_gen.save_manifest(manifest, manifest_path)

        # Upload manifest to FTP
        manifest_remote_path = f"{FTP_UPLOAD_PATH}/manifest.json"
        logger.info(f"📤 Uploading manifest.json to {manifest_remote_path}...")

        if ftp.upload_file(manifest_path, manifest_remote_path):
            logger.info("✅ Manifest uploaded successfully")
        else:
            logger.error("❌ Manifest upload failed")

        # Disconnect FTP
        ftp.disconnect()

        # Cleanup old files
        logger.info("")
        logger.info("=" * 60)
        logger.info("Cleaning up old files")
        logger.info("=" * 60)

        cleanup = FileCleanup(retention_days=RETENTION_DAYS)
        deleted, failed = cleanup.cleanup_uploaded_directory(PDF_DIRECTORY, dry_run=False)

        logger.info(f"Cleanup: {deleted} files deleted, {failed} failed")

        # Log summary
        logger.info("")
        logger.info("=" * 60)
        logger.info("Upload Summary:")
        logger.info(f"  Total files found: {stats['total']}")
        logger.info(f"  Successfully uploaded: {stats['uploaded']}")
        logger.info(f"  Skipped (already uploaded): {stats['skipped']}")
        logger.info(f"  Failed: {stats['failed']}")
        logger.info(f"  Manifest reports: {len(manifest['reports'])}")
        logger.info("=" * 60)

        # Send email notification if enabled
        if EMAIL_ENABLED and all([EMAIL_USERNAME, EMAIL_PASSWORD, EMAIL_FROM, EMAIL_TO]):
            try:
                email_notifier = EmailNotifier(
                    smtp_server=EMAIL_SMTP_SERVER,
                    smtp_port=EMAIL_SMTP_PORT,
                    username=EMAIL_USERNAME,
                    password=EMAIL_PASSWORD,
                    from_email=EMAIL_FROM,
                    to_email=EMAIL_TO
                )

                email_notifier.send_upload_summary(
                    stats=stats,
                    manifest_count=len(manifest['reports']),
                    errors=error_messages if error_messages else None
                )
            except Exception as e:
                logger.error(f"Failed to send email notification: {str(e)}")
        elif EMAIL_ENABLED:
            logger.warning("Email notifications enabled but missing required credentials")

        # Exit with appropriate code
        sys.exit(0 if stats['failed'] == 0 else 1)

    except KeyboardInterrupt:
        logger.info("Operation cancelled by user")
        sys.exit(130)
    except Exception as e:
        logger.error(f"❌ Unexpected error: {str(e)}")
        logger.exception(e)
        sys.exit(1)


if __name__ == "__main__":
    main()
