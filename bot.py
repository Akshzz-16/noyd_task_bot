import discord
from discord.ext import commands
from discord import app_commands
from discord.ui import View, Button, Select
import sqlite3
from datetime import datetime
from config import TOKEN

# ================= DATABASE =================
conn = sqlite3.connect("noyd_tasks.db")
cursor = conn.cursor()

# --- USER ROLES TABLE ---
cursor.execute("""
CREATE TABLE IF NOT EXISTS user_roles (
    user_id INTEGER PRIMARY KEY,
    role TEXT
)
""")
conn.commit()

# ================= ROLE HELPERS =================
def get_user_role(user_id: int) -> str:
    cursor.execute(
        "SELECT role FROM user_roles WHERE user_id=?",
        (user_id,)
    )
    row = cursor.fetchone()
    return row[0] if row else "user"

def is_admin(user_id: int) -> bool:
    return get_user_role(user_id) in ("admin", "superuser")

# ================= BOT SETUP =================
intents = discord.Intents.default()
intents.message_content = True

class NOYDBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        await self.tree.sync()
        print("✅ Slash commands synced")

bot = NOYDBot()

@bot.event
async def on_ready():
    # 🔒 SET SUPERUSER ONCE
    SUPERUSER_ID = 755988808993996830  # 🔴 PUT YOUR DISCORD USER ID HERE

    cursor.execute(
        "INSERT OR IGNORE INTO user_roles (user_id, role) VALUES (?, ?)",
        (SUPERUSER_ID, "superuser")
    )
    conn.commit()

    print(f"🚀 NOYD Task Bot online as {bot.user}")

# ================= UI COMPONENTS =================

class TaskActionView(View):
    def __init__(self, task_id, status, user_id):
        super().__init__(timeout=60)
        self.add_item(StartButton(task_id, status, user_id))
        self.add_item(DoneButton(task_id, status, user_id))

class StartButton(Button):
    def __init__(self, task_id, status, user_id):
        super().__init__(label="▶ Start", style=discord.ButtonStyle.primary)
        self.task_id = task_id
        self.status = status
        self.user_id = user_id

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("⛔ Not your task.", ephemeral=True)
            return

        new_status = "in_progress" if self.status != "in_progress" else "todo"

        cursor.execute(
            "UPDATE tasks SET status=? WHERE id=?",
            (new_status, self.task_id)
        )
        conn.commit()

        await interaction.response.send_message(
            f"🔄 Task #{self.task_id} → **{new_status.upper()}**",
            ephemeral=True
        )

class DoneButton(Button):
    def __init__(self, task_id, status, user_id):
        super().__init__(label="✅ Done", style=discord.ButtonStyle.success)
        self.task_id = task_id
        self.status = status
        self.user_id = user_id

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("⛔ Not your task.", ephemeral=True)
            return

        new_status = "done" if self.status != "done" else "todo"

        cursor.execute(
            "UPDATE tasks SET status=?, completed_at=? WHERE id=?",
            (
                new_status,
                datetime.now().isoformat() if new_status == "done" else None,
                self.task_id
            )
        )
        conn.commit()

        await interaction.response.send_message(
            f"🎉 Task #{self.task_id} → **{new_status.upper()}**",
            ephemeral=True
        )

class TaskSelect(Select):
    def __init__(self, tasks, user_id):
        options = [
            discord.SelectOption(
                label=f"#{task_id} — {title}",
                description=f"Status: {status.upper()}",
                value=str(task_id)
            )
            for task_id, title, status in tasks
        ]

        super().__init__(
            placeholder="Select a task to manage",
            min_values=1,
            max_values=1,
            options=options
        )
        self.user_id = user_id

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("⛔ Not your task list.", ephemeral=True)
            return

        task_id = int(self.values[0])

        cursor.execute(
            "SELECT status FROM tasks WHERE id=?",
            (task_id,)
        )
        status = cursor.fetchone()[0]

        await interaction.response.send_message(
            f"🛠️ Manage Task #{task_id}",
            view=TaskActionView(task_id, status, self.user_id),
            ephemeral=True
        )

class TaskSelectView(View):
    def __init__(self, tasks, user_id):
        super().__init__(timeout=120)
        self.add_item(TaskSelect(tasks, user_id))

# ================= SLASH COMMANDS =================

@bot.tree.command(name="task_create", description="Create a new task")
@app_commands.describe(title="Task title", member="Assign task to user")
async def task_create(interaction: discord.Interaction, title: str, member: discord.Member):
    if not is_admin(interaction.user.id):
        await interaction.response.send_message("⛔ Admin access required.", ephemeral=True)
        return

    cursor.execute(
        "INSERT INTO tasks (title, assigned_to, created_by, status, created_at) VALUES (?, ?, ?, ?, ?)",
        (title, member.id, interaction.user.id, "todo", datetime.now().isoformat())
    )
    conn.commit()

    await interaction.response.send_message(
        f"📝 Task **{title}** assigned to {member.mention}"
    )

@bot.tree.command(name="my_tasks", description="View and manage your tasks")
async def my_tasks(interaction: discord.Interaction):
    cursor.execute(
        "SELECT id, title, status FROM tasks WHERE assigned_to=?",
        (interaction.user.id,)
    )
    tasks = cursor.fetchall()

    if not tasks:
        await interaction.response.send_message("📭 You have no tasks.")
        return

    embed = discord.Embed(
        title="🗂️ Your Tasks",
        description="Select a task below to manage it",
        color=discord.Color.blue()
    )

    for task_id, title, status in tasks:
        embed.add_field(
            name=f"#{task_id} — {title}",
            value=f"Status: **{status.upper()}**",
            inline=False
        )

    await interaction.response.send_message(
        embed=embed,
        view=TaskSelectView(tasks, interaction.user.id)
    )

# ================= ADMIN ROLE COMMANDS =================

@bot.tree.command(name="grant_admin", description="Grant admin rights")
@app_commands.describe(member="User to promote")
async def grant_admin(interaction: discord.Interaction, member: discord.Member):
    if get_user_role(interaction.user.id) != "superuser":
        await interaction.response.send_message("⛔ Only superuser can grant admin.", ephemeral=True)
        return

    cursor.execute(
        "INSERT OR REPLACE INTO user_roles (user_id, role) VALUES (?, ?)",
        (member.id, "admin")
    )
    conn.commit()

    await interaction.response.send_message(f"✅ {member.mention} is now an **ADMIN**")

@bot.tree.command(name="revoke_admin", description="Revoke admin rights")
@app_commands.describe(member="Admin to demote")
async def revoke_admin(interaction: discord.Interaction, member: discord.Member):
    if get_user_role(interaction.user.id) != "superuser":
        await interaction.response.send_message("⛔ Only superuser can revoke admin.", ephemeral=True)
        return

    cursor.execute(
        "DELETE FROM user_roles WHERE user_id=? AND role='admin'",
        (member.id,)
    )
    conn.commit()

    await interaction.response.send_message(f"🔻 {member.mention} is no longer an admin")


@bot.tree.command(name="task_delete", description="Delete a task (ADMIN ONLY)")
@app_commands.describe(
    task_id="ID of the task to delete",
    confirm="Type DELETE to confirm"
)
async def task_delete(
    interaction: discord.Interaction,
    task_id: int,
    confirm: str
):
    # ✅ Immediately acknowledge (prevents timeout)
    await interaction.response.defer(ephemeral=True)

    try:
        # ---- PERMISSION CHECK ----
        if not is_admin(interaction.user.id):
            await interaction.followup.send(
                "⛔ Admin access required."
            )
            return

        # ---- CONFIRMATION CHECK ----
        if confirm != "DELETE":
            await interaction.followup.send(
                "❌ Deletion aborted. You must type `DELETE` exactly."
            )
            return

        # ---- TASK EXISTS CHECK ----
        cursor.execute(
            "SELECT title FROM tasks WHERE id=?",
            (task_id,)
        )
        task = cursor.fetchone()

        if not task:
            await interaction.followup.send(
                "❌ Task not found."
            )
            return

        task_title = task[0]

        # ---- DELETE TASK ----
        cursor.execute(
            "DELETE FROM tasks WHERE id=?",
            (task_id,)
        )
        conn.commit()

        await interaction.followup.send(
            f"🗑️ Task #{task_id} (**{task_title}**) deleted successfully."
        )

    except Exception as e:
        # 🔴 If anything goes wrong, we still respond
        await interaction.followup.send(
            f"⚠️ Error occurred: `{e}`"
        )
        print("DELETE ERROR:", e)


@bot.tree.command(name="whoissuper", description="Show the superuser")
async def whoissuper(interaction: discord.Interaction):
    cursor.execute(
        "SELECT user_id FROM user_roles WHERE role='superuser'"
    )
    row = cursor.fetchone()

    if not row:
        await interaction.response.send_message("❌ No superuser found.")
        return

    user_id = row[0]
    user = await bot.fetch_user(user_id)

    embed = discord.Embed(
        title="👑 Superuser",
        description=f"**{user.name}#{user.discriminator}**",
        color=discord.Color.gold()
    )
    embed.set_thumbnail(url=user.display_avatar.url)

    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="whoisadmin", description="Show current admins")
async def whoisadmin(interaction: discord.Interaction):
    cursor.execute(
        "SELECT user_id FROM user_roles WHERE role='admin'"
    )
    rows = cursor.fetchall()

    if not rows:
        await interaction.response.send_message("ℹ️ No admins assigned.")
        return

    admin_ids = [row[0] for row in rows]
    admins = [await bot.fetch_user(uid) for uid in admin_ids]

    # 🔹 If only ONE admin → show avatar
    if len(admins) == 1:
        admin = admins[0]
        embed = discord.Embed(
            title="🛡️ Admin",
            description=f"**{admin.name}#{admin.discriminator}**",
            color=discord.Color.blue()
        )
        embed.set_thumbnail(url=admin.display_avatar.url)

        await interaction.response.send_message(embed=embed)

    # 🔹 Multiple admins → list usernames
    else:
        names = "\n".join(
            f"• {admin.name}#{admin.discriminator}"
            for admin in admins
        )

        embed = discord.Embed(
            title="🛡️ Admins",
            description=names,
            color=discord.Color.blue()
        )

        await interaction.response.send_message(embed=embed)

# ================= RUN BOT =================
bot.run(TOKEN)
