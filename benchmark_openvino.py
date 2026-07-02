#!/usr/bin/env python3
"""Benchmark a local OpenVINO model with explicit load/unload to avoid OOM."""

import argparse
import gc
import os
import resource
import time

import openvino
from optimum.intel import OVModelForCausalLM
from transformers import AutoTokenizer

DEFAULT_MODEL = "/home/jprajzne/models/qwen3-30b-a3b-int4-ov"

PROMPTS = [
    "What is the capital of France?",
    "Explain quantum computing in two sentences.",
    "Write a short haiku about the ocean.",
]


def mem_gb():
    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return rss / (1024 * 1024)


def load_model(model_path, device="CPU"):
    print(f"Loading model from {model_path} on {device}...")
    print(f"  RSS before load: {mem_gb():.1f} GB")
    t0 = time.perf_counter()

    tokenizer = AutoTokenizer.from_pretrained(model_path, local_files_only=True)

    ov_config = {
        "PERFORMANCE_HINT": "LATENCY",
        "NUM_STREAMS": "1",
    }
    if device == "CPU":
        ov_config["INFERENCE_NUM_THREADS"] = str(os.cpu_count())

    model = OVModelForCausalLM.from_pretrained(
        model_path,
        device=device,
        local_files_only=True,
        ov_config=ov_config,
    )

    load_time = time.perf_counter() - t0
    print(f"  RSS after load:  {mem_gb():.1f} GB")
    print(f"  Model loaded in {load_time:.1f}s")
    return model, tokenizer, load_time


def unload_model(model, tokenizer):
    del model
    del tokenizer
    gc.collect()
    print(f"Model unloaded. RSS: {mem_gb():.1f} GB")


def run_prompt(model, tokenizer, prompt, max_new_tokens):
    messages = [{"role": "user", "content": prompt}]
    text = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    inputs = tokenizer(text, return_tensors="pt")
    num_input_tokens = inputs["input_ids"].shape[1]

    t0 = time.perf_counter()
    outputs = model.generate(**inputs, max_new_tokens=max_new_tokens, do_sample=False)
    elapsed = time.perf_counter() - t0

    new_tokens = outputs.shape[1] - num_input_tokens
    response = tokenizer.decode(outputs[0][num_input_tokens:], skip_special_tokens=True)
    tps = new_tokens / elapsed if elapsed > 0 else 0

    return {
        "prompt": prompt,
        "response": response,
        "input_tokens": num_input_tokens,
        "output_tokens": new_tokens,
        "elapsed": elapsed,
        "tokens_per_sec": tps,
    }


def main():
    parser = argparse.ArgumentParser(description="Benchmark an OpenVINO model")
    parser.add_argument("--model", default=DEFAULT_MODEL, help="Path to OpenVINO model directory")
    parser.add_argument(
        "--device",
        default="CPU",
        help="OpenVINO device (CPU recommended — GPU is integrated and shares system RAM)",
    )
    parser.add_argument("--max-tokens", type=int, default=128, help="Max new tokens per prompt")
    parser.add_argument(
        "--prompt", action="append", help="Custom prompt (repeatable, overrides defaults)"
    )
    args = parser.parse_args()

    prompts = args.prompt if args.prompt else PROMPTS

    print(f"OpenVINO {openvino.__version__}")
    print(f"Device: {args.device}")
    print(f"Max new tokens: {args.max_tokens}")
    print(f"Prompts: {len(prompts)}")
    print()

    model, tokenizer, load_time = load_model(args.model, args.device)

    results = []
    try:
        for i, prompt in enumerate(prompts, 1):
            print(f"\n--- Prompt {i}/{len(prompts)} ---")
            print(f"Q: {prompt}")
            result = run_prompt(model, tokenizer, prompt, args.max_tokens)
            results.append(result)
            print(f"A: {result['response'][:200]}{'...' if len(result['response']) > 200 else ''}")
            print(
                f"   {result['input_tokens']} in / {result['output_tokens']} out | "
                f"{result['elapsed']:.2f}s | {result['tokens_per_sec']:.1f} tok/s"
            )
    finally:
        print()
        unload_model(model, tokenizer)

    print()
    print("=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"Model load time:   {load_time:.1f}s")
    total_out = sum(r["output_tokens"] for r in results)
    total_time = sum(r["elapsed"] for r in results)
    avg_tps = total_out / total_time if total_time > 0 else 0
    print(f"Total generation:  {total_out} tokens in {total_time:.2f}s")
    print(f"Average throughput: {avg_tps:.1f} tok/s")
    for r in results:
        print(f"  [{r['tokens_per_sec']:5.1f} tok/s] {r['prompt'][:60]}")


if __name__ == "__main__":
    main()
