import os
import re
import io
import discord
import asyncio
import traceback
import datetime
import pytz
from discord.ext import commands
from discord.ui import View, Select, Button
from flask import Flask
import threading

# ==== 설정 ====
TOKEN = os.getenv("BOT_TOKEN")  # 환경변수에 토큰 넣어주세요
CATEGORY_ID = 1398263224062836829  # 티켓 생성할 카테고리 ID (정수)
TICKET_CATEGORY_NAME = "⠐ 💳 = 이용하기"  # 카테고리 없을 때 생성할 이름
LOG_CHANNEL_ID = 1398267597299912744  # 로그 채널 ID
ADMIN_ROLE_ID = 123456789012345678  # 관리자 역할 ID (옵션)
OWNER_ROLE_ID = 987654321098765432  # 오너 역할 ID (옵션)
UPDATE_INTERVAL = 5  # 임베드 시간 갱신 초 (5초)
MAX_LOG_MESSAGES = 1000  # 채팅 로그 저장 시 가져올 최대 메시지 수
# ==============

intents = discord.Intents.default()
intents.messages = True
intents.guilds = True
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)
kst = pytz.timezone('Asia/Seoul')

# ---- keepalive (Flask) ----
app = Flask(__name__)

@app.route('/')
def home():
    return "✅ Bot is running!"

def run_web():
    port = int(os.getenv("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

def keep_alive():
    threading.Thread(target=run_web, daemon=True).start()

# ---------- Helpers ----------
def sanitize_channel_name(s: str) -> str:
    # 허용 문자만 남기고 공백은 대시로
    s = s.lower()
    s = re.sub(r'[^a-z0-9\-_ ]', '', s)
    s = s.replace(' ', '-')
    return s[:90]

def korean_now_str():
    # 요청하신 포맷: 08월 11일 04:16:05
    now = datetime.datetime.now(kst)
    return now.strftime("%m월 %d일 %H:%M:%S")

async def save_channel_logs_and_send(channel: discord.TextChannel, log_channel: discord.TextChannel):
    """
    ticket 채널의 최근 메시지들을 텍스트로 저장해 로그 채널에 업로드합니다.
    """
    try:
        msgs = []
        async for m in channel.history(limit=MAX_LOG_MESSAGES, oldest_first=True):
            # created_at은 UTC이므로 KST로 변환
            timestamp = m.created_at.astimezone(kst).strftime("%Y-%m-%d %H:%M:%S")
            author = f"{m.author} ({m.author.id})"
            content = m.content or ""
            att_urls = " ".join(att.url for att in m.attachments) if m.attachments else ""
            line = f"[{timestamp}] {author}: {content} {att_urls}"
            msgs.append(line)
        if not msgs:
            txt = "채팅 기록이 비어 있습니다."
        else:
            txt = "\n".join(msgs)
        bio = io.BytesIO(txt.encode("utf-8"))
        bio.seek(0)
        fname = f"ticket-log-{channel.name}.txt"
        await log_channel.send(content=f"🗂 티켓 로그: {channel.name}", file=discord.File(fp=bio, filename=fname))
    except Exception:
        traceback.print_exc()

# ---------- UI 컴포넌트 ----------
class CloseTicketButton(Button):
    def __init__(self):
        # custom_id 지정해서 persistent 하게 만듭니다.
        super().__init__(label="티켓 닫기", style=discord.ButtonStyle.danger, emoji="🔒", custom_id="wind_close_ticket_v1")

    async def callback(self, interaction: discord.Interaction):
        # 티켓 닫을 때: 로그 저장 -> 로그채널에 파일 업로드 -> 채널 삭제
        await interaction.response.defer(ephemeral=True)
        channel = interaction.channel
        if not channel or not channel.name.startswith("ticket-"):
            await interaction.followup.send("이 버튼은 티켓 채널에서만 사용할 수 있습니다.", ephemeral=True)
            return

        log_channel = bot.get_channel(LOG_CHANNEL_ID)
        # 관리자/운영진에게 알람 및 로그 업로드
        try:
            if log_channel:
                await log_channel.send(embed=discord.Embed(
                    title="티켓 닫힘 (예정)",
                    description=f"채널 `{channel.name}`이(가) 닫힙니다. 로그를 저장합니다...",
                    color=0x000000
                ))
                await save_channel_logs_and_send(channel, log_channel)
        except Exception:
            traceback.print_exc()

        # 실제 채널 삭제 (오류 핸들링)
        try:
            await channel.delete()
        except Exception as e:
            traceback.print_exc()
            # 실패 시 관리자에게 알림
            if log_channel:
                await log_channel.send(embed=discord.Embed(
                    title="티켓 채널 삭제 실패",
                    description=f"채널 `{channel.name}` 삭제 중 오류가 발생했습니다:\n```\n{e}\n```",
                    color=discord.Color.red()
                ))

class ShopSelect(Select):
    def __init__(self):
        options = [
            discord.SelectOption(label="구매하기", description="로블록스 아이템 또는 로벅스 구매", emoji="🛒"),
            discord.SelectOption(label="문의하기", description="문의사항 티켓 열기", emoji="🎫"),
            discord.SelectOption(label="파트너 & 상단배너", description="파트너 또는 상단배너 문의", emoji="👑")
        ]
        # custom_id 지정 -> persistent
        super().__init__(placeholder="원하는 항목을 선택하세요", options=options, custom_id="wind_shop_select_v1")

    async def callback(self, interaction: discord.Interaction):
        # 선택 시 티켓 생성 (중복방지: 같은 유저가 이미 가진 티켓 탐지)
        selected_item = self.values[0]
        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild
        if not guild:
            await interaction.followup.send("길드 정보가 없습니다.", ephemeral=True)
            return

        # 우선 카테고리 가져오기 (ID 우선)
        category = None
        try:
            if CATEGORY_ID:
                category = guild.get_channel(int(CATEGORY_ID))
                if category and not isinstance(category, discord.CategoryChannel):
                    category = None
        except Exception:
            category = None

        if not category:
            category = discord.utils.get(guild.categories, name=TICKET_CATEGORY_NAME)
            if not category:
                try:
                    category = await guild.create_category(TICKET_CATEGORY_NAME)
                except Exception:
                    category = None

        # 중복 방지: 같은 유저의 기존 ticket- 채널이 있는지 검사
        def user_has_ticket_channel():
            uname = interaction.user.name.lower()
            uid = str(interaction.user.id)
            for ch in guild.channels:
                if not isinstance(ch, discord.TextChannel):
                    continue
                cname = ch.name.lower()
                # 유저 이름 혹은 id가 들어간 티켓 채널을 같은 유저의 것으로 판단
                if cname.startswith("ticket-") and (uname in cname or uid in cname or ch.permissions_for(interaction.user).read_messages):
                    return ch
            return None

        existing_channel = user_has_ticket_channel()
        if existing_channel:
            try:
                await interaction.followup.send(f"⚠ 이미 티켓이 존재합니다: {existing_channel.mention}", ephemeral=True)
            except Exception:
                await interaction.followup.send("⚠ 이미 티켓이 존재합니다 (채널을 표시할 수 없음).", ephemeral=True)
            return

        # 채널 이름 생성: 항목-유저이름-유저id 로 유니크하게
        base = f"ticket-{selected_item}-{interaction.user.name}-{interaction.user.id}"
        channel_name = sanitize_channel_name(base)

        # 만약 동일 이름 채널이 이미 있으면 (희박) 뒤에 타임스탬프 추가
        if discord.utils.get(guild.channels, name=channel_name):
            channel_name = sanitize_channel_name(f"{channel_name}-{int(datetime.datetime.now().timestamp())}")

        # 권한 설정: 기본 비공개, 유저 허용, 봇 허용, 관리자/오너 역할 허용
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            interaction.user: discord.PermissionOverwrite(read_messages=True, send_messages=True),
            guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True)
        }
        try:
            if ADMIN_ROLE_ID:
                admin_role = guild.get_role(int(ADMIN_ROLE_ID))
                if admin_role:
                    overwrites[admin_role] = discord.PermissionOverwrite(read_messages=True, send_messages=True)
            if OWNER_ROLE_ID:
                owner_role = guild.get_role(int(OWNER_ROLE_ID))
                if owner_role:
                    overwrites[owner_role] = discord.PermissionOverwrite(read_messages=True, send_messages=True)
        except Exception:
            # role 접근 문제 무시하고 진행
            traceback.print_exc()

        # 티켓 채널 생성
        try:
            ticket_channel = await guild.create_text_channel(channel_name, category=category, overwrites=overwrites)
        except Exception as e:
            traceback.print_exc()
            await interaction.followup.send("채널 생성 중 오류가 발생했습니다. 관리자에게 문의하세요.", ephemeral=True)
            log_ch = bot.get_channel(LOG_CHANNEL_ID)
            if log_ch:
                await log_ch.send(embed=discord.Embed(title="티켓 채널 생성 실패", description=str(e), color=discord.Color.red()))
            return

        # 티켓 안내 임베드 (검정)
        guide_embed = discord.Embed(
            title=f"{selected_item} 티켓 생성됨",
            description="💬 담당자가 곧 응답할 예정입니다.\n아래 버튼을 눌러 티켓을 닫을 수 있습니다.",
            color=0x000000
        ).set_footer(text="WIND Ticket Bot")
        try:
            await ticket_channel.send(embed=guide_embed, view=View().add_item(CloseTicketButton()))
        except Exception:
            # 만약 전송 실패해도 생성은 된 상태 — 로그 기록
            traceback.print_exc()

        try:
            await interaction.followup.send(f"✅ `{selected_item}` 티켓이 생성되었습니다: {ticket_channel.mention}", ephemeral=True)
        except Exception:
            # ephemeral 전송 실패하면 간단 텍스트로 알려줌 (fallback)
            await interaction.channel.send("✅ 티켓이 생성되었습니다.")

        # 생성 로그
        try:
            log_channel = bot.get_channel(LOG_CHANNEL_ID)
            if log_channel:
                await log_channel.send(embed=discord.Embed(
                    title="📥 티켓 생성",
                    description=f"**채널:** {ticket_channel.mention}\n**생성자:** {interaction.user.mention} ({interaction.user.id})\n**항목:** `{selected_item}`\n**시간:** {korean_now_str()}",
                    color=0x000000
                ))
        except Exception:
            traceback.print_exc()

# View (persistent)
class ShopView(View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(ShopSelect())

# ---------- 시간 갱신 루프 (메시지 임베드) ----------
async def update_message_time_loop(message: discord.Message):
    while True:
        try:
            await asyncio.sleep(UPDATE_INTERVAL)
            # 최신 메시지 fetch (삭제되면 종료)
            try:
                msg = await message.channel.fetch_message(message.id)
            except discord.NotFound:
                break
            if not msg.embeds:
                break
            e = msg.embeds[0]
            embed = discord.Embed(title=e.title, description=e.description, color=e.color or 0x000000)
            # 원래의 다른 필드들은 유지
            for field in e.fields:
                if field.name != "현재 시간":
                    embed.add_field(name=field.name, value=field.value, inline=field.inline)
            embed.add_field(name="현재 시간", value=korean_now_str(), inline=False)
            try:
                await msg.edit(embed=embed, view=msg.components[0] if msg.components else None)
            except Exception:
                # 에러 발생시 로그만 남기고 루프 종료
                traceback.print_exc()
                break
        except asyncio.CancelledError:
            break
        except Exception:
            traceback.print_exc()
            break

# ---------- 커맨드 ----------
@bot.command(name="상점")
async def shop_cmd(ctx: commands.Context):
    embed = discord.Embed(
        title="WIND RBX 상점",
        description="아래에서 원하는 항목을 선택하세요",
        color=0x000000
    )
    embed.add_field(name="현재 시간", value=korean_now_str(), inline=False)

    view = ShopView()
    try:
        message = await ctx.send(embed=embed, view=view)
    except Exception:
        # 권한 문제 등으로 전송 실패 시 사용자에게 알림
        await ctx.send("임베드 전송 실패 — 권한을 확인하세요.")
        return

    # bot이 재시작되어도 persistent view가 작동하도록 등록
    try:
        bot.add_view(view)
    except Exception:
        pass

    # 백그라운드에서 시간 갱신 시작
    bot.loop.create_task(update_message_time_loop(message))

# ---------- on_ready ----------
@bot.event
async def on_ready():
    # 재시작시에도 view 등록 (persistent)
    try:
        bot.add_view(ShopView())
    except Exception:
        pass
    print(f"✅ 로그인됨: {bot.user} (ID: {bot.user.id})")

# 실행
keep_alive()
bot.run(TOKEN)
