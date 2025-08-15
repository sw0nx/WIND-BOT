import os
import discord
from discord.ext import commands
from discord import app_commands

TOKEN = os.getenv("BOT_TOKEN")

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)


class TicketSelect(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label="문의", description="문의 티켓 열기"),
            discord.SelectOption(label="신고", description="신고 티켓 열기"),
            discord.SelectOption(label="기타", description="기타 티켓 열기"),
        ]
        super().__init__(
            placeholder="티켓 유형을 선택하세요",
            min_values=1,
            max_values=1,
            options=options
        )

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.send_message(
            f"**{self.values[0]}** 티켓이 생성되었습니다!", ephemeral=True
        )


class TicketView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(TicketSelect())


@bot.event
async def on_ready():
    print(f"✅ 봇 로그인: {bot.user}")
    try:
        synced = await bot.tree.sync()
        print(f"Slash Commands 동기화 완료: {len(synced)}개")
    except Exception as e:
        print(f"Slash 동기화 오류: {e}")


@bot.tree.command(name="티켓", description="티켓 생성 메뉴를 표시합니다.")
async def ticket(interaction: discord.Interaction):
    await interaction.response.send_message(
        "티켓 항목을 선택하세요 ↓", 
        view=TicketView()
    )


bot.run(TOKEN)
