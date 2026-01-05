# ai/exaone_loader.py
import os

# ✅ torch/transformers import 전에 GPU를 아예 숨김 (cuDNN DLL 이슈 회피)
os.environ["CUDA_VISIBLE_DEVICES"] = ""

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer


class ExaoneLoader:
    _instance = None
    _model = None
    _tokenizer = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(ExaoneLoader, cls).__new__(cls)
            cls._instance._load_model()
        return cls._instance

    def _load_model(self):
        print("[ExaoneLoader] Loading LGAI-EXAONE/EXAONE-4.0-1.2B model...")
        model_id = "LGAI-EXAONE/EXAONE-4.0-1.2B"

        try:
            self._tokenizer = AutoTokenizer.from_pretrained(model_id, trust_remote_code=True)
            self._model = AutoModelForCausalLM.from_pretrained(
                model_id,
                torch_dtype=torch.float32,  # ✅ CPU 안정
                device_map="cpu",           # ✅ auto 금지
                trust_remote_code=True,
                low_cpu_mem_usage=True,
            )
            self._model.eval()
            print("✅ Model loaded successfully. (CPU)")
        except Exception as e:
            print(f"❌ Failed to load model: {e}")
            self._model = None
            self._tokenizer = None

    def generate_content(self, prompt: str) -> str:
        if not self._model or not self._tokenizer:
            return "모델이 로드되지 않았습니다."

        messages = [{"role": "user", "content": prompt}]
        input_ids = self._tokenizer.apply_chat_template(
            messages,
            tokenize=True,
            add_generation_prompt=True,
            return_tensors="pt"
        )

        with torch.inference_mode():
            output_ids = self._model.generate(
                input_ids,  # ✅ 이미 CPU
                max_new_tokens=64,
                eos_token_id=self._tokenizer.eos_token_id,
                do_sample=True,
                temperature=0.3,
                top_p=0.8
            )

        response = self._tokenizer.decode(
            output_ids[0][len(input_ids[0]):],
            skip_special_tokens=True
        )
        return response.strip()
