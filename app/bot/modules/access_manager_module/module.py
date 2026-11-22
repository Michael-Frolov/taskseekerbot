from .._base_module import BaseModule

import json
from html import escape

class AccessManagerModule(BaseModule):
    def check_triggers(self, message):
        command = self.get_command(message)
        if self.check_command(command, "/access"):
            return True, command
        return False, command
    
    async def _proceed(self, command: list[str]) -> tuple[str, str]:
        try:
            if command and len(command) and command[0].lower() == "/access":
                
                modules = ("global", *self.bot.modules)
                if len(command) > 1 and command[1] in modules:
                    
                    if command[1].lower() == modules[0].lower():
                        access_settings = self.bot.settings["access"]
                    else:
                        access_settings = self.bot.modules[command[1]].settings["access"]
                    
                    if not len(command) > 2:
                        return f"{command[1]} access settings:\n<pre>{escape(json.dumps(access_settings, indent=4))}</pre>", "HTML"
                    
                    if not command[1].lower() == modules[0] and isinstance(self.bot.modules[command[1]], AccessManagerModule):
                        return f"❌ {command[1]} access settings are not allowed for editing.", None
                    
                    setting_names = {
                        "enabled": (access_settings, "enabled"),
                        "devsonly": (access_settings, "devs_only"),
                        "users": (access_settings["categories"], "users"),
                        "groups": (access_settings["categories"], "groups"),
                        "supergroups": (access_settings["categories"], "supergroups"),
                        "bots": (access_settings, "allow_bots"),
                        "notifications": (access_settings, "noaccess_notif")
                    }
                    limit_name = "limit"
                    setting_actions = ("allow", "deny")
                    exception_actions = ("allow", "deny", "clear")
                    clear_action = "clear"
                    if command[2].lower() in (*setting_names, *exception_actions, limit_name):
                        
                        global_dif = ("enabled", "notifications", "limit")
                        if command[1].lower() == modules[0].lower() and command[2].lower() in global_dif:
                            return f"❌ {command[1]} has no '{command[2]}' setting.", None
                        
                        if command[2].lower() in setting_names:
                            if len(command) > 3 and command[3].lower() in setting_actions:
                                
                                setting_value = command[3].lower() == exception_actions[0]
                                target, key = setting_names[command[2].lower()]
                                target[key] = setting_value
                                
                                if command[1].lower() == modules[0].lower():
                                    await self.bot.save_settings()
                                else:
                                    await self.bot.modules[command[1]].save_settings()
                                
                                return f"✅ {command[1]} access setting '{command[2]}' set to {str(setting_value)} successfully.", None
                            
                            else: return f"{" ".join([*command[0:3]])} {setting_actions}", None
                        
                        if command[2].lower() == limit_name:
                            if len(command) > 3:
                                
                                if command[3].lower() == clear_action:
                                    access_settings["limit"] = None
                                    
                                    if command[1].lower() == modules[0].lower():
                                        await self.bot.save_settings()
                                    else:
                                        await self.bot.modules[command[1]].save_settings()
                                    
                                    return f"✅ {command[1]} access setting '{command[2]}' set to {str(access_settings["limit"])} successfully.", None
                                
                                if len(command) > 4:
                                    try:
                                        access_settings["limit"] = {
                                            "rate": int(command[3]),
                                            "span": float(command[4])
                                        }
                                        
                                        if command[1].lower() == modules[0].lower():
                                            await self.bot.save_settings()
                                        else:
                                            await self.bot.modules[command[1]].save_settings()
                                        
                                        return f"✅ {command[1]} access setting '{command[2]}' set to {str(access_settings["limit"])} successfully.", None
                                        
                                    except ValueError:
                                        return f"❌ Rate and span values must be int and float respectively.", None
                                        
                                else: return f"{" ".join([*command[0:4]])} {("{RateValue}")}", None
                            
                            else: return f"{" ".join([*command[0:3]])} {(clear_action, "{RateValue}")}", None
                        
                        if command[2].lower() in exception_actions:
                            if len(command) > 3:
                                
                                args = command[3:]
                                ids_proceed = set()
                                ids_failed = set()
                                for id in args:
                                    try:
                                        ids_proceed.add(int(id))
                                    except ValueError:
                                        ids_failed.add(id)
                                
                                if command[2].lower() == exception_actions[0].lower():
                                    for id in ids_proceed:
                                        if id not in access_settings["exceptions_pos"]:
                                            access_settings["exceptions_pos"].append(id)
                                        if id in access_settings["exceptions_neg"]:
                                            access_settings["exceptions_neg"].remove(id)
                                
                                if command[2].lower() == exception_actions[1].lower():
                                    for id in ids_proceed:
                                        if id not in access_settings["exceptions_neg"]:
                                            access_settings["exceptions_neg"].append(id)
                                        if id in access_settings["exceptions_pos"]:
                                            access_settings["exceptions_pos"].remove(id)
                                
                                if command[2].lower() == exception_actions[2].lower():
                                    for id in ids_proceed:
                                        if id in access_settings["exceptions_pos"]:
                                            access_settings["exceptions_pos"].remove(id)
                                        if id in access_settings["exceptions_neg"]:
                                            access_settings["exceptions_neg"].remove(id)
                                
                                if command[1].lower() == modules[0].lower():
                                    await self.bot.save_settings()
                                else:
                                    await self.bot.modules[command[1]].save_settings()
                                
                                return f"✅ Proceed successfully ({len(ids_proceed)}).\n❌ Failed ({len(ids_failed)})", None
                                
                            else: return f"{" ".join([*command[0:3]])} ('{self.bot.settings["bot"]["id"]}')", None
                    
                    else: return f"{" ".join([*command[0:2]])} {(*setting_names, *setting_actions, limit_name)}", None

                else: return f"{command[0]} {modules}", None
            
        except IndexError:
            return "❌ Not enough arguments.", None
        except KeyError as exc:
            return f"❌ Not found {exc}.", None
        except Exception as exc:
            return f"❌ Error occured: {exc}.", None
        
        return "❌ Command wasn't executed propely.", None
    
    async def run(self, message, command, timeout):
        
        result = await self._proceed(command)
        return await self.bot.telegram_connect.reply_to_message(message, result[0], parse_mode=result[1])
    
    async def close(self):
        return