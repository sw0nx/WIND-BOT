import os
import discord
from discord.ext import commands, tasks
from discord.ui import View, Select, Button
import datetime
import pytz
from flask import Flask
import threading
import asyncio

# ==== 설정 ====
TOKEN = os.getenv("BOT_TOKEN")  # Zeabur 환경변수 지원
TICKET_CATEGORY_NAME = "⠐ 💳 = 이용하기"
LOG_CHANNEL_ID = 1398267597299912744
ADMIN_ROLE_ID = 123456789012345678
OWNER_ROLE_ID = 987654321098765432
AUTO_CLOSE_HOURS = 24  # 티켓 자동 닫기 시간
# ==============

intents = discord.Intents.default()
intents.messages = True
intents.guilds = True
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)
kst = pytz.timezone('Asia/Seoul')

# ==== Flask 서버 (Zeabur용) ====
app = Flask(__name__)

@app.route('/')
def home():
    return "✅ Bot is running on Zeabur!"

def run_web():
    port = int(os.getenv("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

def keep_alive():
    threading.Thread(target=run_web).start()
# ==================================

# ====== 버튼 클래스 ======
class CloseTicketButton(Button):
    def __init__(self):
        super().__init__(label="티켓 닫기", style=discord.ButtonStyle.danger, emoji="🔒")

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        if interaction.channel.name.startswith("ticket-"):
            log_channel = bot.get_channel(LOG_CHANNEL_ID)
            now_kst = datetime.datetime.now(kst)
            if log_channel:
                await log_channel.send(
                    embed=discord.Embed(
                        title="티켓 닫힘",
                        description=f"**채널:** {interaction.channel.name}\n"
                                    f"**닫은 유저:** {interaction.user.mention} (`{interaction.user}`)\n"
                                    f"**시간:** {now_kst.strftime('%Y년 %m월 %d일 %H:%M:%S')}",
                        color=0x000000
                    )
                )
            await interaction.channel.delete()

# ====== 셀렉트 메뉴 클래스 ======
class ShopSelect(Select):
    def __init__(self):
        options = [
            discord.SelectOption(label="구매하기", description="로블록스 아이템 또는 로벅스 구매", emoji="🛒"),
            discord.SelectOption(label="문의하기", description="문의사항 티켓 열기", emoji="🎫"),
            discord.SelectOption(label="파트너 & 상단배너", description="파트너 또는 상단배너 문의", emoji="👑")
        ]
        super().__init__(placeholder="원하는 항목을 선택하세요", options=options)

    async def callback(self, interaction: discord.Interaction):
        selected_item = self.values[0]
        await interaction.response.defer(ephemeral=True)

        guild = interaction.guild
        category = discord.utils.get(guild.categories, name=TICKET_CATEGORY_NAME) or await guild.create_category(TICKET_CATEGORY_NAME)

        ticket_name = f"ticket-{interaction.user.name}"
        existing_ticket = discord.utils.get(guild.channels, name=ticket_name)
        if existing_ticket:
            await interaction.followup.send(f"⚠ 이미 티켓이 존재합니다: {existing_ticket.mention}", ephemeral=True)
            return

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            interaction.user: discord.PermissionOverwrite(read_messages=True, send_messages=True),
            guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True)
        }
        ticket_channel = await guild.create_text_channel(ticket_name, category=category, overwrites=overwrites)

        admin_role = guild.get_role(ADMIN_ROLE_ID)
        owner_role = guild.get_role(OWNER_ROLE_ID)
        now_kst = datetime.datetime.now(kst)

        # 알림 임베드
        mention_embed = discord.Embed(
            title="티켓 알림",
            description=f"{admin_role.mention if admin_role else ''} {owner_role.mention if owner_role else ''}\n"
                        f"💬 담당자가 곧 응답할 예정입니다.",
            color=0x000000
        )
        mention_embed.add_field(name="티켓 생성자", value=f"{interaction.user.mention} (`{interaction.user}`)", inline=True)
        mention_embed.add_field(name="선택 항목", value=selected_item, inline=True)
        mention_embed.add_field(name="생성 시간", value=now_kst.strftime("%Y년 %m월 %d일 %H:%M:%S"), inline=False)
        await ticket_channel.send(embed=mention_embed)

        # 안내 임베드
        guide_embed = discord.Embed(
            title=f"{selected_item} 티켓 생성됨",
            description=f"{interaction.user.mention}님의 요청입니다.\n아래 버튼을 눌러 티켓을 닫을 수 있습니다.",
            color=0x000000
        )
        guide_embed.set_footer(text="WIND Ticket Bot")
        await ticket_channel.send(embed=guide_embed, view=View(timeout=None).add_item(CloseTicketButton()))

        await interaction.followup.send(f"✅ `{selected_item}` 항목의 티켓이 생성되었습니다: {ticket_channel.mention}", ephemeral=True)

        # 로그
        log_channel = bot.get_channel(LOG_CHANNEL_ID)
        if log_channel:
            await log_channel.send(
                embed=discord.Embed(
                    title="📥 티켓 생성",
                    description=f"**채널:** {ticket_channel.mention}\n"
                                f"**생성자:** {interaction.user.mention} (`{interaction.user}`)\n"
                                f"**항목:** `{selected_item}`\n"
                                f"**시간:** {now_kst.strftime('%Y년 %m월 %d일 %H:%M:%S')}",
                    color=0x000000
                )
            )

        # 자동 닫기 예약
        await asyncio.sleep(AUTO_CLOSE_HOURS * 3600)
        if ticket_channel and ticket_channel.exists():
            await ticket_channel.send("⏳ 시간이 초과되어 티켓이 자동으로 닫힙니다.")
            await ticket_channel.delete()

# ====== 뷰 클래스 ======
class ShopView(View):
    def __init__(self):
        super().__init__(timeout=None)  # 무제한 작동
        self.add_item(ShopSelect())

# ====== 명령어 ======
@bot.command()
@commands.has_permissions(administrator=True)
async def 상점(ctx):
    now_kst = datetime.datetime.now(kst)
    time_str = now_kst.strftime("%Y년 %m월 %d일 %H:%M:%S")

    embed = discord.Embed(
        title="WIND RBX 상점",
        description="아래에서 원하는 항목을 선택하세요",
        color=0x000000
    )
    embed.add_field(name="현재 시간", value=time_str, inline=False)
    message = await ctx.send(embed=embed, view=ShopView())

    # 5초마다 한국어 시간 갱신
    while True:
        await asyncio.sleep(5)
        now_kst = datetime.datetime.now(kst)
        time_str = now_kst.strftime("%Y년 %m월 %d일 %H:%M:%S")
        embed.set_field_at(0, name="현재 시간", value=time_str, inline=False)
        await message.edit(embed=embed, view=ShopView())

# ====== 봇 상태 표시 ======
@tasks.loop(seconds=60)
async def update_status():
    total_tickets = sum(1 for ch in bot.get_all_channels() if ch.name.startswith("ticket-"))
    await bot.change_presence(
        activity=discord.Game(name=f"🎫 티켓 {total_tickets}개 처리 중")
    )

@bot.event
async def on_ready():
    print(f"✅ {bot.user} 로 로그인됨")
    update_status.start()

# 실행
keep_alive()
bot.run(TOKEN)
