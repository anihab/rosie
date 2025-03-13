## Rosie

A helpful discord bot dedicated to helping user's manage their time. Can set reminders, pomodoro-style timers, reaction roles, and poll to schedule time-zone sensitive events for long distance friends!

## Contents

- [1. Running](#running)
- [2. Privacy Policy and Terms of Service](#privacy-policy-and-terms-of-service)

## Running

You can invite Rosie to your server with this [invite URL](https://discord.com/oauth2/authorize?client_id=1306658573945667585&scope=bot&permissions=140392229988)!

I've provided this code primarily for educational purposes and would prefer you not to run an instance of this bot, it's simpler to just se the invite URL to have it on your server. However, if an instance of the bot is needed the installation steps are as follows:

1. **Ensure you have Python 3.11 or higher.**

2. **Install dependencies.**

```
pip install -U -r requirements.txt
```

3. **Create a .env in the root directory**

The env should include the following:

```
TOKEN= # Your bot's private token
GID= # Your test guild/server ID 
```

4. **Create a ```config.json``` file in the root directory.**

The file should follow the template provided below:

```
{
    "prefix": "!",
    "invite_link": "",  # your bot's invite link
    "owner_id": # your user ID
  }
```

## Privacy Policy and Terms of Service

### Privacy Policy

Rosie may collect and store the following information in it's database:

1. **Guild and Channel IDs:**

    - These are unique numerical identifiers associated with your server and channels, not their names.

    - This data is stored when provided by the user to enable Rosie to send messages to the correct channels as requested. This applies to features such as reaction roles, reminders, and event notifications.

    - **Data Deletion:** This data is automatically deleted when reminders and events expire, are canceled, or finalized. For reaction role messages, the associated data is deleted when the message itself is removed or when the server administrator manually runs a command to clear the database.

2. **User IDs:**

    - These are unique numerical identifiers, not your username, tag, or display name.

    - If a user opts to set reminders or creates an event message, their User ID may be stored to ensure reminders are delivered correctly.

    - **Data Deletion:** This data is automatically deleted when the associated reminders and events expire, are canceled, or finalized.

### Data Usage and Retention

- The stored data is used exclusively for providing Rosie’s functionalities as intended.

- Rosie **does not** share, sell, or distribute any stored information to third parties.

- If a server removes Rosie, all related stored data may be deleted upon request.

### Your Rights and Control

- Server administrators can request deletion of any stored data by contacting the bot owner.

- Users can revoke Rosie’s permissions or remove Rosie from a server at any time.

---

### Terms of Service
By using Rosie, you agree to the following terms:

1. **Usage and Limitations**

    - Rosie is provided as-is, with no guarantees of uptime, availability, or performance.

    - The bot should not be used for illegal, malicious, or abusive activities.

2. **User Responsibility**

    - Users are responsible for configuring Rosie correctly within their servers.

    - Server administrators must ensure that Rosie’s usage complies with Discord’s Terms of Service.

3. **Service Modification and Termination**

    - The bot owner reserves the right to update, modify, or discontinue Rosie’s features at any time without prior notice.

    - The bot owner may also restrict access to Rosie for users or servers found violating these terms.

By continuing to use Rosie, you acknowledge and agree to these terms. If you do not agree, you should discontinue using Rosie immediately. For any concerns or data removal requests, please contact the bot owner.
