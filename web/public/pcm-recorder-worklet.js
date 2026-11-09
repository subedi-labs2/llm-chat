// Converts microphone audio to 16-bit mono PCM at 24 kHz in ~100 ms chunks for /api/transcribe.
// Loaded with audioWorklet.addModule() by src/lib/transcribe.ts. On a "flush" message it posts
// the partial chunk (if any), then "flushed", and ignores further input.
const TARGET_RATE = 24000;
const CHUNK_SAMPLES = 2400;

class PcmRecorder extends AudioWorkletProcessor {
  constructor() {
    super();
    this.ratio = sampleRate / TARGET_RATE;
    this.phase = 0;
    this.sum = 0;
    this.count = 0;
    this.chunk = new Int16Array(CHUNK_SAMPLES);
    this.length = 0;
    this.flushed = false;
    this.port.onmessage = (event) => {
      if (event.data !== "flush" || this.flushed) return;
      this.flushed = true;
      if (this.length > 0) {
        const partial = this.chunk.slice(0, this.length);
        this.port.postMessage(partial.buffer, [partial.buffer]);
      }
      this.port.postMessage("flushed");
    };
  }

  push(sample) {
    const clamped = Math.max(-1, Math.min(1, sample));
    this.chunk[this.length++] =
      clamped < 0 ? clamped * 0x8000 : clamped * 0x7fff;
    if (this.length === CHUNK_SAMPLES) {
      this.port.postMessage(this.chunk.buffer, [this.chunk.buffer]);
      this.chunk = new Int16Array(CHUNK_SAMPLES);
      this.length = 0;
    }
  }

  process(inputs) {
    const input = inputs[0]?.[0];
    if (!input || this.flushed) return true;
    // Downsample by averaging the input samples that fall into each output sample.
    for (const sample of input) {
      this.sum += sample;
      this.count += 1;
      this.phase += 1;
      while (this.phase >= this.ratio) {
        this.push(this.count ? this.sum / this.count : sample);
        this.sum = 0;
        this.count = 0;
        this.phase -= this.ratio;
      }
    }
    return true;
  }
}

registerProcessor("pcm-recorder", PcmRecorder);
