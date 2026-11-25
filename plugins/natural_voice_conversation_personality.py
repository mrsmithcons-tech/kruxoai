import json
import logging

PLUGIN = {
    "name": "natural_voice_conversation_personality",
    "description": "Configures and manages JARVIS's natural voice conversation personality traits inspired by stonic-ai, enabling realistic tone, dynamic speech rate, and contextual empathy.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "tone": {
                "type": "STRING",
                "description": "The desired conversation tone (e.g., 'casual', 'professional', 'empathetic', 'enthusiastic')."
            },
            "speech_rate": {
                "type": "NUMBER",
                "description": "Speech speed rate between 0.5 (slow) and 2.0 (fast). Default is 1.0."
            },
            "filler_words": {
                "type": "BOOLEAN",
                "description": "Whether to allow natural filler words (e.g., 'hmm', 'well') for a human-like voice feel."
            },
            "context_memory": {
                "type": "STRING",
                "description": "Specific contextual background or personality persona settings to adopt."
            }
        }
    }
}

def run(parameters: dict, player=None, session_memory=None) -> str:
    """
    Executes the natural voice conversation personality configuration.
    Updates session memory and UI log with updated Stonic-AI inspired personality settings.
    """
    try:
        tone = parameters.get("tone", "conversational")
        speech_rate = parameters.get("speech_rate", 1.0)
        filler_words = parameters.get("filler_words", True)
        context_memory = parameters.get("context_memory", "Stonic-AI Adaptive Voice Persona")

        # Clamp speech rate within reasonable bounds
        speech_rate = max(0.5, min(2.0, float(speech_rate)))

        # Update session memory if available
        if session_memory is not None and isinstance(session_memory, dict):
            session_memory["voice_personality"] = {
                "tone": tone,
                "speech_rate": speech_rate,
                "filler_words": filler_words,
                "context_memory": context_memory
            }

        status_msg = (
            f"Voice Personality Updated:\n"
            f"- Tone: {tone.capitalize()}\n"
            f"- Speech Rate: {speech_rate}x\n"
            f"- Natural Fillers: {'Enabled' if filler_words else 'Disabled'}\n"
            f"- Persona Context: {context_memory}"
        )

        # Notify UI layer safely if player instance provided
        if player is not None:
            if hasattr(player, "write_log"):
                player.write_log(f"[Plugin] Applied stonic-ai voice personality profile: {tone}")
            if hasattr(player, "show_content"):
                player.show_content("Voice Personality Profile", status_msg)

        return f"I have adapted the stonic-ai voice personality. My tone is now set to {tone} at {speech_rate}x speed."

    except Exception as e:
        error_msg = f"Failed to set voice conversation personality: {str(e)}"
        logging.error(error_msg)
        
        if player is not None and hasattr(player, "write_log"):
            player.write_log(f"[Plugin Error] natural_voice_conversation_personality: {str(e)}")

        return "I encountered an error while updating my voice personality settings."