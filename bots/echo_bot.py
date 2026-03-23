# bots/echo_bot.py
"""Bot echo: risponde ad ogni messaggio ricevuto sul canale configurato."""
import logging
from pubsub import pub

_interface = None
_CHANNEL   = 0

def start(interface, channel: int = 0):
    global _interface, _CHANNEL
    _interface = interface
    _CHANNEL   = channel
    pub.subscribe(_on_message, "meshtastic.receive.text")
    logging.info(f"Echo bot attivo sul canale {channel}")

def stop():
    try:
        pub.unsubscribe(_on_message, "meshtastic.receive.text")
    except Exception:
        pass

def _on_message(packet, interface):
    if _interface is None:
        return
    try:
        decoded = packet.get("decoded", {})
        text    = decoded.get("text", "")
        src     = packet.get("fromId", "unknown")
        channel = packet.get("channel", 0)
        if channel != _CHANNEL or not text:
            return
        # Non rispondere ai propri messaggi
        local = _interface.getMyNodeInfo()
        if src == local.get("user", {}).get("id"):
            return
        _interface.sendText(f"[echo] {text}", channelIndex=channel, destinationId=src)
    except Exception as e:
        logging.error(f"Echo bot errore: {e}")
