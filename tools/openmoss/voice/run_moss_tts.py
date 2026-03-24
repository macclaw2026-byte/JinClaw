#!/usr/bin/env python3

from __future__ import annotations

import argparse
import importlib.util
import sys
from pathlib import Path


def _load_torch():
    import torch

    torch.backends.cuda.enable_cudnn_sdp(False)
    torch.backends.cuda.enable_flash_sdp(True)
    torch.backends.cuda.enable_mem_efficient_sdp(True)
    torch.backends.cuda.enable_math_sdp(True)
    return torch


def resolve_attn_implementation(torch, device: str, dtype) -> str:
    if (
        device == "cuda"
        and importlib.util.find_spec("flash_attn") is not None
        and dtype in {torch.float16, torch.bfloat16}
    ):
        major, _ = torch.cuda.get_device_capability()
        if major >= 8:
            return "flash_attention_2"
    if device == "cuda":
        return "sdpa"
    return "eager"


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a single MOSS-TTS synthesis job")
    parser.add_argument("--text", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--tts-repo", required=True)
    parser.add_argument("--model-path", default="OpenMOSS-Team/MOSS-TTS")
    parser.add_argument("--codec-model-path", default="OpenMOSS-Team/MOSS-Audio-Tokenizer")
    args = parser.parse_args()

    tts_repo = Path(args.tts_repo).expanduser().resolve()
    if not tts_repo.exists():
        raise SystemExit(f"tts repo missing: {tts_repo}")
    if str(tts_repo) not in sys.path:
        sys.path.insert(0, str(tts_repo))

    torch = _load_torch()
    import torchaudio
    from transformers import AutoModel, AutoProcessor

    device = "cuda" if torch.cuda.is_available() else "cpu"
    dtype = torch.bfloat16 if device == "cuda" else torch.float32
    attn_implementation = resolve_attn_implementation(torch, device, dtype)

    processor = AutoProcessor.from_pretrained(
        args.model_path,
        trust_remote_code=True,
    )
    if hasattr(processor, "audio_tokenizer") and processor.audio_tokenizer is not None:
        processor.audio_tokenizer = processor.audio_tokenizer.to(device)

    model = AutoModel.from_pretrained(
        args.model_path,
        trust_remote_code=True,
        attn_implementation=attn_implementation,
        torch_dtype=dtype,
    ).to(device)
    model.eval()

    conversations = [[processor.build_user_message(text=args.text)]]
    batch = processor(conversations, mode="generation")
    input_ids = batch["input_ids"].to(device)
    attention_mask = batch["attention_mask"].to(device)

    with torch.no_grad():
        outputs = model.generate(
            input_ids=input_ids,
            attention_mask=attention_mask,
            max_new_tokens=4096,
        )

    messages = processor.decode(outputs)
    if not messages:
        raise RuntimeError("MOSS-TTS returned no decoded messages")

    audio = messages[0].audio_codes_list[0]
    out_path = Path(args.output).expanduser()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    torchaudio.save(str(out_path), audio.unsqueeze(0), processor.model_config.sampling_rate)
    print(out_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
