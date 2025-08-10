import os
import re
import discord
from discord.ext import commands
from discord.ui import View, Select, Button
import datetime
import pytz
from flask import Flask
import threading
import asyncio

# ==== 설정 ====
TOKEN = os.getenv("BOT_TOKEN")  # 환경변수로 토큰 설정
CATEGORY_ID = 1398263224062836829
TICKET_CATEGORY_NAME = "⠐ 💳 = 이용하기"
LOG_CHANNEL_ID = 1398267597299912744
UPDATE_INTERVAL = 5  # 5초마다 시간 갱신
# ==============

intents = discord.Intents.default()
intents.messages = True
intents.guilds = True
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)
kst = pytz.timezone('Asia/Seoul')

# ==== Flask (keep-alive) ====
app = Flask(__name__)
@app.route('/')
def home():
    return "✅ Bot is running!"

def run_web():
    port = int(os.getenv("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

def keep_alive():
    threading.Thread(target=run_web, daemon=True).start()

# ---------- Helper ----------
def sanitize_channel_name(s: str) -> str:
    s = s.lower()
    s = re.sub(r'[^a-z0-9\- _]', '', s)
    s = s.replace(' ', '-')
    return s[:90]

def korean_now_str():
    now = datetime.datetime.now(kst)
    return now.strftime("%Y년 %m월 %d일 %H:%M:%S")

# ---------- UI ----------
class CloseTicketButton(Button):
    def __init__(self):
        super().__init__(label="티켓 닫기", style=discord.ButtonStyle.danger, emoji="🔒", custom_id="wind_close_ticket")

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        if interaction.channel and interaction.channel.name.startswith("ticket-"):
            log_channel = bot.get_channel(LOG_CHANNEL_ID)
            if log_channel:
                await log_channel.send(
                    embed=discord.Embed(
                        title="티켓 닫힘",
                        description=f"**채널:** {interaction.channel.name}\n"
                                    f"**닫은 유저:** {interaction.user.mention}\n"
                                    f"**시간:** {korean_now_str()}",
                        color=0x000000
                    )
                )
            try:
                await interaction.channel.delete()
            except:
                pass

class ShopSelect(Select):
    def __init__(self):
        options = [
            discord.SelectOption(label="구매하기", description="로블록스 아이템 또는 로벅스 구매", emoji="🛒"),
            discord.SelectOption(label="문의하기", description="문의사항 티켓 열기", emoji="🎫"),
            discord.SelectOption(label="파트너 & 상단배너", description="파트너 또는 상단배너 문의", emoji="👑")
        ]
        super().__init__(placeholder="원하는 항목을 선택하세요", options=options, custom_id="wind_shop_select")

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        guild = interaction.guild
        category = guild.get_channel(int(CATEGORY_ID))
        if not category or not isinstance(category, discord.CategoryChannel):
            category = discord.utils.get(guild.categories, name=TICKET_CATEGORY_NAME)
            if not category:
                category = await guild.create_category(TICKET_CATEGORY_NAME)

        channel_name = sanitize_channel_name(f"ticket-{self.values[0]}-{interaction.user.name}")
        if discord.utils.get(guild.channels, name=channel_name):
            await interaction.followup.send(f"⚠ 이미 티켓이 존재합니다.", ephemeral=True)
            return

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            interaction.user: discord.PermissionOverwrite(read_messages=True, send_messages=True),
            guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True)
        }
        ticket_channel = await guild.create_text_channel(channel_name, category=category, overwrites=overwrites)

        now_ts = int(datetime.datetime.now(kst).timestamp())
        mention_embed = discord.Embed(
            title="티켓 알림",
            description="💬 담당자가 곧 응답할 예정입니다.",
            color=0x000000
        )
        mention_embed.add_field(name="선택 항목", value=self.values[0], inline=True)
        mention_embed.add_field(name="생성 시간", value=f"<t:{now_ts}:F>", inline=False)
        await ticket_channel.send(embed=mention_embed)

        guide_embed = discord.Embed(
            title=f"{self.values[0]} 티켓 생성됨",
            description=f"{interaction.user.mention}님의 요청입니다.\n아래 버튼을 눌러 티켓을 닫을 수 있습니다.",
            color=0x000000
        ).set_footer(text="WIND Ticket Bot")
        await ticket_channel.send(embed=guide_embed, view=View().add_item(CloseTicketButton()))

        await interaction.followup.send(f"✅ `{self.values[0]}` 티켓이 생성되었습니다: {ticket_channel.mention}", ephemeral=True)

        log_channel = bot.get_channel(LOG_CHANNEL_ID)
        if log_channel:
            await log_channel.send(
                embed=discord.Embed(
                    title="📥 티켓 생성",
                    description=f"**채널:** {ticket_channel.mention}\n**생성자:** {interaction.user.mention}\n**항목:** `{self.values[0]}`\n**시간:** {korean_now_str()}",
                    color=0x000000
                )
            )

class ShopView(View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(ShopSelect())

# ---------- Update Time Loop ----------
async def update_message_time_loop(message: discord.Message):
    while True:
        await asyncio.sleep(UPDATE_INTERVAL)
        try:
            message = await message.channel.fetch_message(message.id)
        except discord.NotFound:
            break
        if not message.embeds:
            break
        e = message.embeds[0].copy()
        found_idx = None
        for i, f in enumerate(e.fields):
            if f.name == "현재 시간":
                found_idx = i
                break
        if found_idx is not None:
            e.set_field_at(found_idx, name="현재 시간", value=korean_now_str(), inline=False)
        else:
            e.add_field(name="현재 시간", value=korean_now_str(), inline=False)
        try:
            await message.edit(embed=e, view=message.components[0] if message.components else None)
        except:
            break

# ---------- Command ----------
@bot.command(name="상점")
async def shop_cmd(ctx: commands.Context):
    embed = discord.Embed(
        title="WIND RBX 상점",
        description="아래에서 원하는 항목을 선택하세요",
        color=0x000000
    )
    embed.add_field(name="현재 시간", value=korean_now_str(), inline=False)
    embed.add_field(name="선택 항목", value="아직 선택 안 함", inline=False)

    view = ShopView()
    message = await ctx.send(embed=embed, view=view)
    bot.add_view(view)
    bot.loop.create_task(update_message_time_loop(message))

# ---------- On Ready ----------
@bot.event
async def on_ready():
    bot.add_view(ShopView())
    print(f"✅ 로그인됨: {bot.user} (ID: {bot.user.id})")

# 실행
keep_alive()
bot.run(TOKEN)
