UNAVAILABLE = "Audio analysis isn’t available for this recording. Upload an audio file you’re authorized to use."


def availability(has_asset: bool, analysis_allowed: bool, playback_allowed: bool) -> dict:
    """Analysis and playback are separate permissions; a streaming link or metadata hit grants neither."""
    analysis = bool(has_asset and analysis_allowed)
    playback = bool(has_asset and playback_allowed)
    return {"audio_analysis": analysis, "playback": playback, "message": None if analysis else UNAVAILABLE}
