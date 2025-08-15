import os
import discord
from discord.ext import commands
from discord import app_commands
from flask import Flask
import threading

TOKEN = os.getenv("BOT_TOKEN")  # 환경변수 BOT_TOKEN 설정 필수

# ===== Discord Bot 설정 =====
intents = discord.Intents.default()
intents.guilds = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

# ===== 티켓 드롭다운 =====
class TicketDropdown(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label="티켓 생성", value="create_ticket")
        ]
        super().__init__(placeholder="티켓 항목 선택", options=options)

    async def callback(self, interaction: discord.Interaction):
        guild = interaction.guild
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            interaction.user: discord.PermissionOverwrite(read_messages=True)
        }
        channel = await guild.create_text_channel(
            name=f"ticket-{interaction.user.name}",
            overwrites=overwrites
        )
        await interaction.response.send_message(f"✅ 티켓이 생성되었습니다: {channel.mention}", ephemeral=True)

# ===== View =====
class TicketView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(TicketDropdown())

# ===== 슬래시 명령어 =====
@bot.tree.command(name="티켓", description="티켓 메뉴를 엽니다.")
async def ticket(interaction: discord.Interaction):
    embed = discord.Embed(
        description="아래 드롭다운중 하나를 선택해 티켓을 열어주세요.\n\n티켓에서 맨션시 티켓닫습니다",
        color=0x2b2d31
    )
    await interaction.response.send_message(embed=embed, view=TicketView())

# ===== 봇 준비 이벤트 =====
@bot.event
async def on_ready():
    await bot.tree.sync()
    print(f"✅ 로그인 완료: {bot.user}")

# ===== Flask Keep-Alive =====
app = Flask('')

@app.route('/')
def home():
    return "Bot is running!"

def run():
    app.run(host='0.0.0.0', port=8080)

def keep_alive():
    t = threading.Thread(target=run)
    t.start()

# ===== 실행 =====
if __name__ == "__main__":
    keep_alive()
    bot.run(TOKEN)
