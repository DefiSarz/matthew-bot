import os
import asyncio
import logging
from typing import Dict, List, Optional
import tempfile
import shutil
from urllib.parse import urlparse

import yt_dlp
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler, 
    CallbackQueryHandler, ContextTypes, filters
)

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Bot configuration
BOT_TOKEN = "YOUR_BOT_TOKEN_HERE"  # Replace with your actual bot token
MAX_FILE_SIZE = 2 * 1024 * 1024 * 1024  # 500MB extended file size limit

class MediaDownloader:
    def __init__(self):
        self.supported_platforms = {
            'youtube.com': 'YouTube',
            'youtu.be': 'YouTube',
            'twitter.com': 'Twitter/X',
            'x.com': 'Twitter/X',
            'tiktok.com': 'TikTok',
            'newgrounds.com': 'Newgrounds'
        }
    
    def get_platform(self, url: str) -> Optional[str]:
        """Identify the platform from URL"""
        parsed = urlparse(url)
        domain = parsed.netloc.lower().replace('www.', '')
        
        for platform_domain, platform_name in self.supported_platforms.items():
            if platform_domain in domain:
                return platform_name
        return None
    
    async def get_video_info(self, url: str) -> Dict:
        """Extract video information without downloading"""
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'extract_flat': False,
        }
        
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = await asyncio.to_thread(ydl.extract_info, url, download=False)
                return info
        except Exception as e:
            logger.error(f"Error extracting info: {e}")
            return {}
    
    async def download_media(self, url: str, format_id: str, output_path: str) -> Optional[str]:
        """Download media with specified format"""
        ydl_opts = {
            'outtmpl': os.path.join(output_path, '%(title)s.%(ext)s'),
            'format': format_id,
            'quiet': True,
            'no_warnings': True,
        }
        
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = await asyncio.to_thread(ydl.extract_info, url)
                filename = ydl.prepare_filename(info)
                return filename if os.path.exists(filename) else None
        except Exception as e:
            logger.error(f"Download error: {e}")
            return None

class TelegramBot:
    def __init__(self):
        self.downloader = MediaDownloader()
        self.user_sessions = {}  # Store user session data
    
    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /start command"""
        welcome_text = """
🤖 **Matthew Bot - Multi-Platform Media Downloader**

Send me a URL from:
• YouTube
• Twitter/X
• TikTok
• Newgrounds

I'll extract available formats and let you choose quality and format!

**Commands:**
/help - Show this help message
/cancel - Cancel current operation

Just paste a URL to get started! 🚀
        """
        await update.message.reply_text(welcome_text, parse_mode='Markdown')
    
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /help command"""
        help_text = """
**How to use:**

1. Send me a URL from supported platforms
2. Choose your preferred format (video/audio)
3. Select quality and resolution
4. Download and enjoy!

**Supported platforms:**
• YouTube (youtube.com, youtu.be)
• Twitter/X (twitter.com, x.com)
• TikTok (tiktok.com)
• Newgrounds (newgrounds.com)

**File size limit:** 500MB
**Supported formats:** MP4, MP3, WEBM, M4A, and more!

Note: Some platforms may have restrictions on certain content.
        """
        await update.message.reply_text(help_text, parse_mode='Markdown')
    
    async def cancel_operation(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /cancel command"""
        user_id = update.effective_user.id
        if user_id in self.user_sessions:
            del self.user_sessions[user_id]
            await update.message.reply_text("❌ Operation cancelled.")
        else:
            await update.message.reply_text("No operation to cancel.")
    
    async def handle_url(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle URL messages"""
        url = update.message.text.strip()
        user_id = update.effective_user.id
        
        # Validate URL
        platform = self.downloader.get_platform(url)
        if not platform:
            await update.message.reply_text(
                "❌ Unsupported platform. Please send a URL from:\n"
                "• YouTube\n• Twitter/X\n• TikTok\n• Newgrounds"
            )
            return
        
        # Send processing message
        processing_msg = await update.message.reply_text(
            f"🔍 Processing {platform} URL...\nThis may take a moment."
        )
        
        try:
            # Extract video info
            info = await self.downloader.get_video_info(url)
            if not info:
                await processing_msg.edit_text("❌ Failed to extract video information.")
                return
            
            # Store session data
            self.user_sessions[user_id] = {
                'url': url,
                'info': info,
                'platform': platform
            }
            
            # Create format selection keyboard
            keyboard = self.create_format_keyboard(info)
            
            title = info.get('title', 'Unknown Title')[:50]
            duration = info.get('duration', 0)
            duration_str = f"{duration//60}:{duration%60:02d}" if duration else "Unknown"
            
            text = f"📹 **{title}**\n\n"
            text += f"🎬 Platform: {platform}\n"
            text += f"⏱ Duration: {duration_str}\n\n"
            text += "Choose format and quality:"
            
            await processing_msg.edit_text(
                text,
                reply_markup=keyboard,
                parse_mode='Markdown'
            )
            
        except Exception as e:
            logger.error(f"Error processing URL: {e}")
            await processing_msg.edit_text(
                "❌ Error processing URL. Please try again or check if the URL is valid."
            )
    
    def create_format_keyboard(self, info: Dict) -> InlineKeyboardMarkup:
        """Create inline keyboard for format selection"""
        keyboard = []
        
        # Audio formats
        keyboard.append([InlineKeyboardButton("🎵 Audio Only", callback_data="category_audio")])
        
        # Video formats
        keyboard.append([InlineKeyboardButton("🎬 Video", callback_data="category_video")])
        
        # Cancel button
        keyboard.append([InlineKeyboardButton("❌ Cancel", callback_data="cancel")])
        
        return InlineKeyboardMarkup(keyboard)
    
    def create_quality_keyboard(self, info: Dict, category: str) -> InlineKeyboardMarkup:
        """Create keyboard for quality selection"""
        keyboard = []
        formats = info.get('formats', [])
        
        if category == "audio":
            # Audio formats
            audio_formats = []
            for f in formats:
                if f.get('acodec') != 'none' and f.get('vcodec') == 'none':
                    quality = f.get('abr', 'Unknown')
                    ext = f.get('ext', 'unknown')
                    filesize = f.get('filesize') or f.get('filesize_approx', 0)
                    
                    if filesize and filesize <= MAX_FILE_SIZE:
                        size_mb = filesize / (1024 * 1024)
                        button_text = f"🎵 {ext.upper()} - {quality}kbps ({size_mb:.1f}MB)"
                        audio_formats.append((button_text, f['format_id']))
            
            # Sort by quality (descending)
            audio_formats.sort(key=lambda x: x[1], reverse=True)
            
            for text, format_id in audio_formats[:5]:  # Limit to 5 options
                keyboard.append([InlineKeyboardButton(text, callback_data=f"download_{format_id}")])
        
        elif category == "video":
            # Video formats
            video_formats = []
            for f in formats:
                if f.get('vcodec') != 'none':
                    height = f.get('height', 0)
                    ext = f.get('ext', 'unknown')
                    filesize = f.get('filesize') or f.get('filesize_approx', 0)
                    
                    if filesize and filesize <= MAX_FILE_SIZE and height:
                        size_mb = filesize / (1024 * 1024)
                        button_text = f"📹 {height}p {ext.upper()} ({size_mb:.1f}MB)"
                        video_formats.append((button_text, f['format_id'], height))
            
            # Sort by resolution (descending)
            video_formats.sort(key=lambda x: x[2], reverse=True)
            
            for text, format_id, _ in video_formats[:5]:  # Limit to 5 options
                keyboard.append([InlineKeyboardButton(text, callback_data=f"download_{format_id}")])
        
        # Back and Cancel buttons
        keyboard.append([
            InlineKeyboardButton("⬅ Back", callback_data="back"),
            InlineKeyboardButton("❌ Cancel", callback_data="cancel")
        ])
        
        return InlineKeyboardMarkup(keyboard)
    
    async def handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle callback queries"""
        query = update.callback_query
        await query.answer()
        
        user_id = update.effective_user.id
        data = query.data
        
        if data == "cancel":
            if user_id in self.user_sessions:
                del self.user_sessions[user_id]
            await query.edit_message_text("❌ Operation cancelled.")
            return
        
        if user_id not in self.user_sessions:
            await query.edit_message_text("❌ Session expired. Please send the URL again.")
            return
        
        session = self.user_sessions[user_id]
        info = session['info']
        
        if data == "back":
            # Go back to format selection
            keyboard = self.create_format_keyboard(info)
            title = info.get('title', 'Unknown Title')[:50]
            text = f"📹 **{title}**\n\nChoose format and quality:"
            await query.edit_message_text(text, reply_markup=keyboard, parse_mode='Markdown')
        
        elif data.startswith("category_"):
            category = data.replace("category_", "")
            keyboard = self.create_quality_keyboard(info, category)
            title = info.get('title', 'Unknown Title')[:50]
            category_name = "Audio" if category == "audio" else "Video"
            text = f"📹 **{title}**\n\nSelect {category_name} quality:"
            await query.edit_message_text(text, reply_markup=keyboard, parse_mode='Markdown')
        
        elif data.startswith("download_"):
            format_id = data.replace("download_", "")
            await self.download_and_send(query, session, format_id)
    
    async def download_and_send(self, query, session: Dict, format_id: str):
        """Download and send the media file"""
        await query.edit_message_text("⬇️ Downloading... Please wait.")
        
        url = session['url']
        info = session['info']
        
        # Create temporary directory
        temp_dir = tempfile.mkdtemp()
        
        try:
            # Download the file
            filepath = await self.downloader.download_media(url, format_id, temp_dir)
            
            if not filepath or not os.path.exists(filepath):
                await query.edit_message_text("❌ Download failed. Please try again.")
                return
            
            # Check file size
            file_size = os.path.getsize(filepath)
            if file_size > MAX_FILE_SIZE:
                await query.edit_message_text(
                    f"❌ File too large ({file_size/(1024*1024):.1f}MB). "
                    f"Maximum allowed size is {MAX_FILE_SIZE/(1024*1024):.0f}MB."
                )
                return
            
            await query.edit_message_text("📤 Uploading to Telegram...")
            
            # Send the file
            title = info.get('title', 'download')
            caption = f"🎬 {title}\n🔗 From: {session['platform']}"
            
            with open(filepath, 'rb') as file:
                if filepath.lower().endswith(('.mp3', '.m4a', '.wav', '.flac')):
                    await query.message.reply_audio(
                        audio=file,
                        caption=caption,
                        title=title
                    )
                else:
                    await query.message.reply_video(
                        video=file,
                        caption=caption
                    )
            
            await query.edit_message_text("✅ Download completed!")
            
        except Exception as e:
            logger.error(f"Download error: {e}")
            await query.edit_message_text("❌ Download failed. Please try again.")
        
        finally:
            # Cleanup
            if os.path.exists(temp_dir):
                shutil.rmtree(temp_dir, ignore_errors=True)
            
            # Clear session
            user_id = query.from_user.id
            if user_id in self.user_sessions:
                del self.user_sessions[user_id]

def main():
    """Main function to run the bot"""
    if BOT_TOKEN == "YOUR_BOT_TOKEN_HERE":
        print("❌ Please replace BOT_TOKEN with your actual bot token!")
        return
    
    # Create bot instance
    bot = TelegramBot()
    
    # Create application
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Add handlers
    application.add_handler(CommandHandler("start", bot.start))
    application.add_handler(CommandHandler("help", bot.help_command))
    application.add_handler(CommandHandler("cancel", bot.cancel_operation))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, bot.handle_url))
    application.add_handler(CallbackQueryHandler(bot.handle_callback))
    
    # Start the bot
    print("🚀 Bot is starting...")
    application.run_polling()

if __name__ == '__main__':
    main()
