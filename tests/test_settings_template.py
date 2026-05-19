from pathlib import Path


def test_audio_settings_template_supports_supertonic_and_provider_visibility():
    template = Path("GUI/settings.html").read_text()

    assert 'checks["settings.tts.voice_choice"]["options"]' in template
    assert 'data-tts-providers="Supertonic"' in template
    assert 'data-tts-providers="elevenlabs,OpenAI,tiktok"' in template
    assert 'const voiceChoiceSelect = document.getElementById(\'voiceChoiceSelect\');' in template
    assert 'applyTtsVisibility();' in template


def test_threads_settings_template_supports_discovery_specific_credentials():
    template = Path("GUI/settings.html").read_text()

    assert 'id="threadsDiscoveryMethodSelect"' in template
    assert 'data-discovery-methods="api"' in template
    assert 'data-discovery-methods="scrape"' in template
    assert 'data-preserve-hidden="true"' in template
    assert 'name="threads.creds.user_id"' in template
    assert 'Screenshots still reuse your saved Threads username/password.' in template
    assert "el.disabled = !isThreads || (!matches && !preserveHidden);" in template
    assert 'const threadsDiscoveryMethodSelect = document.getElementById(\'threadsDiscoveryMethodSelect\');' in template
    assert 'applyThreadsDiscoveryVisibility();' in template