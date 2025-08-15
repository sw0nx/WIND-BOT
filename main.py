import discord
from discord import app_commands
from discord.ext import commands

TOKEN = "BOT_TOKEN"
GUILD_ID = 1398256208887939214  # 서버 ID

intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)


@bot.event
async def on_ready():
    print(f"✅ 로그인됨: {bot.user}")


@bot.tree.command(name="티켓", description="티켓 안내 메시지를 보냅니다.")
async def ticket_cmd(interaction: discord.Interaction):
    components_v2 = [
        {
            "type": 1,  # Container
            "components": [
                {
                    "type": 2,  # Section
                    "components": [
                        {
                            "type": 3,  # TextDisplay
                            "text":"• 장난문의는 제재될 수 있습니다‼\n"
                                    "• 티켓 열고 잠수/탈주 시 하루 탐아 당할 수 있습니다‼"
                        },
                        { "type": 4 },  # Separator
                        {
                            "type": 5,  # ActionRow
                            "components": [
                                {
                                    "type": 6,  # StringSelectMenu
                                    "custom_id": "ticket_select_v2",
                                    "placeholder": "원하는 항목을 선택하세요",
                                    "options": [
                                        {
                                            "label": "구매하기",
                                            "value": "buy",
                                            "description": "로블록스 아이템 또는 로벅스 구매",
                                            "emoji": {"name": "🛒"}
                                        }
                                    ]
                                }
                            ]
                        }
                    ]
                }
            ]
        }
    ]

    await interaction.response.send_message(
        components=components_v2,
        flags=discord.MessageFlags.is_components_v2()
    )


@bot.event
async def on_interaction(interaction: discord.Interaction):
    # 드롭다운 선택 시 티켓 채널 생성
    if interaction.type == discord.InteractionType.component and interaction.data.get("custom_id") == "ticket_select_v2":
        value = interaction.data["values"][0]
        if value == "buy":
            guild = interaction.guild
            overwrites = {
                guild.default_role: discord.PermissionOverwrite(read_messages=False),
                interaction.user: discord.PermissionOverwrite(read_messages=True)
            }
            channel = await guild.create_text_channel(
                name=f"ticket-{interaction.user.name}",
                overwrites=overwrites
            )
            await interaction.response.send_message(f"{channel.mention} 채널이 생성되었습니다!", ephemeral=True)


bot.run(TOKEN)
