"""
Application constants for the PythonID bot.

This module contains shared constants used across multiple bot modules,
including permissions, message templates, and formatting utilities.
"""

from telegram import ChatPermissions

# Permissions applied when restricting a user (effectively mutes them)
RESTRICTED_PERMISSIONS = ChatPermissions(
    can_send_messages=False,
    can_send_audios=False,
    can_send_documents=False,
    can_send_photos=False,
    can_send_videos=False,
    can_send_video_notes=False,
    can_send_voice_notes=False,
    can_send_polls=False,
    can_send_other_messages=False,
    can_add_web_page_previews=False,
    can_change_info=False,
    can_invite_users=False,
    can_pin_messages=False,
    can_manage_topics=False,
)

# Missing items separator for Indonesian language
MISSING_ITEMS_SEPARATOR = " dan "


def format_threshold_display(threshold_minutes: int) -> str:
    """
    Format time threshold in minutes to human-readable Indonesian text.
    
    Converts minutes to "X jam" for values >= 60, or "Y menit" for smaller values.
    
    Args:
        threshold_minutes: Time threshold in minutes.
        
    Returns:
        Formatted string like "3 jam" or "30 menit".
    """
    if threshold_minutes >= 60:
        hours = threshold_minutes // 60
        return f"{hours} jam"
    return f"{threshold_minutes} menit"


# Message templates used in warning and restriction scenarios
# Warning mode (default): No restrictions, just warnings
WARNING_MESSAGE_NO_RESTRICTION = (
    "⚠️ Hai {user_mention}, mohon lengkapi {missing_text} kamu "
    "untuk mematuhi aturan grup.\n"
    "Kamu akan dibatasi setelah {threshold_display}.\n\n"
    "📖 [Baca aturan grup]({rules_link})"
)

# Progressive restriction mode: First message warning
WARNING_MESSAGE_WITH_THRESHOLD = (
    "⚠️ Hai {user_mention}, mohon lengkapi {missing_text} kamu "
    "untuk mematuhi aturan grup.\n"
    "Kamu akan dibatasi setelah {warning_threshold} pesan atau {threshold_display}.\n\n"
    "📖 [Baca aturan grup]({rules_link})"
)

# Restriction message when user reaches message threshold
RESTRICTION_MESSAGE_AFTER_MESSAGES = (
    "🚫 {user_mention} telah dibatasi setelah {message_count} pesan.\n"
    "Mohon lengkapi {missing_text} kamu untuk mematuhi aturan grup.\n\n"
    "📖 [Baca aturan grup]({rules_link})\n"
    "✉️ [Hubungi langsung robot untuk membuka pembatasan (mohon pertimbangkan bahwa percakapan dengan robot saat ini sebagian besar belum direkam)]({dm_link})"
)

# Restriction message when user reaches time threshold (scheduler)
RESTRICTION_MESSAGE_AFTER_TIME = (
    "🚫 {user_mention} telah dibatasi karena tidak melengkapi profil "
    "dalam {threshold_display}.\n\n"
    "📖 [Baca aturan grup]({rules_link})\n"
    "✉️ [Hubungi langsung robot untuk membuka pembatasan (mohon pertimbangkan bahwa percakapan dengan robot saat ini sebagian besar belum direkam)]({dm_link})"
)

# Captcha verification message templates
CAPTCHA_WELCOME_MESSAGE = (
    "👋 Selamat datang {user_mention}!\n\n"
    "Untuk memastikan kamu bukan robot, silakan klik tombol di bawah ini "
    "dalam waktu {timeout} detik."
)

CAPTCHA_VERIFIED_MESSAGE = "✅ Terima kasih {user_mention}, verifikasi berhasil! Selamat bergabung."

CAPTCHA_WRONG_USER_MESSAGE = "❌ Tombol ini bukan untukmu."

CAPTCHA_TIMEOUT_MESSAGE = (
    "🚫 {user_mention} tidak menyelesaikan verifikasi dalam waktu yang ditentukan.\n\n"
    "Silakan {dm_link} untuk membuka pembatasan."
)

CAPTCHA_PENDING_DM_MESSAGE = (
    "⏳ Kamu memiliki verifikasi captcha yang tertunda.\n"
    "Silakan cek grup dan tekan tombol verifikasi."
)

CAPTCHA_FAILED_VERIFICATION_MESSAGE = "Gagal memverifikasi. Silakan coba lagi."

# DM handler message templates
DM_NOT_IN_GROUP_MESSAGE = (
    "❌ Kamu belum bergabung di grup.\n"
    "Silakan bergabung ke grup terlebih dahulu."
)

DM_INCOMPLETE_PROFILE_MESSAGE = (
    "❌ Kamu belum memenuhi persyaratan.\n\n"
    "Mohon lengkapi {missing_text} kamu terlebih dahulu, "
    "lalu kirim pesan lagi ke bot ini.\n\n"
    "📖 [Baca aturan grup]({rules_link})"
)

DM_NO_RESTRICTION_MESSAGE = (
    "ℹ️ Kamu tidak memiliki pembatasan dari bot ini.\n"
    "Jika kamu dibatasi oleh admin, silakan hubungi admin grup secara langsung."
)

DM_ALREADY_UNRESTRICTED_MESSAGE = (
    "ℹ️ Kamu sudah tidak dibatasi di grup.\n"
    "Silakan bergabung kembali!"
)

DM_UNRESTRICTION_SUCCESS_MESSAGE = (
    "✅ Selamat! Kamu sudah memenuhi persyaratan.\n"
    "Pembatasan kamu di grup telah dicabut. Silakan bergabung kembali!"
)
