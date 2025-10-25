# AI模型部署指南

## 推荐的AI模型

### 1. 金融情绪分析专用模型

#### **FinBERT** (推荐)
- **模型名称**: `yiyanghkust/finbert-tone`
- **特点**: 专门针对金融文本训练的情绪分析模型
- **优势**: 
  - 在金融领域表现优秀
  - 支持多语言
  - 模型大小适中（约400MB）
- **适用场景**: 股票新闻、财报分析、市场情绪预测

#### **RoBERTa-Financial**
- **模型名称**: `ProsusAI/finbert`
- **特点**: 基于RoBERTa的金融情绪分析模型
- **优势**: 
  - 更强的语言理解能力
  - 支持细粒度情绪分类
  - 适合复杂金融文本

### 2. 通用情绪分析模型

#### **DistilBERT** (轻量级)
- **模型名称**: `distilbert-base-uncased-finetuned-sst-2-english`
- **特点**: 轻量级BERT模型
- **优势**: 
  - 模型小（约250MB）
  - 推理速度快
  - 适合资源有限的环境

#### **BERT-base-chinese** (中文优化)
- **模型名称**: `bert-base-chinese`
- **特点**: 中文优化的BERT模型
- **优势**: 
  - 中文理解能力强
  - 适合中文金融文本
  - 社区支持好

## 部署步骤

### 1. 下载模型

```bash
# 创建模型目录
mkdir -p models/finbert
cd models/finbert

# 使用HuggingFace CLI下载
pip install huggingface_hub
huggingface-cli download yiyanghkust/finbert-tone --local-dir ./finbert-tone
```

### 2. 修改项目配置

在 `src/config.yaml` 中添加模型配置：

```yaml
ai:
  provider: "local"  # 使用本地模型
  local_model_path: "models/finbert/finbert-tone"
  model_name: "yiyanghkust/finbert-tone"
  max_length: 512
  batch_size: 16
```

### 3. 创建本地AI客户端

创建 `src/ai/local_ai_client.py`：

```python
import torch
from transformers import AutoTokenizer, AutoModelForSequenceClassification
from typing import List
import numpy as np

class LocalAIClient:
    def __init__(self, model_path: str):
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.tokenizer = AutoTokenizer.from_pretrained(model_path)
        self.model = AutoModelForSequenceClassification.from_pretrained(model_path)
        self.model.to(self.device)
        self.model.eval()
    
    def classify_sentiment(self, texts: List[str]) -> List[float]:
        """对文本进行情绪分析"""
        results = []
        
        for text in texts:
            inputs = self.tokenizer(
                text, 
                return_tensors="pt", 
                truncation=True, 
                padding=True, 
                max_length=512
            ).to(self.device)
            
            with torch.no_grad():
                outputs = self.model(**inputs)
                probabilities = torch.softmax(outputs.logits, dim=-1)
                sentiment_score = probabilities[0][1].item() - probabilities[0][0].item()
                results.append(sentiment_score)
        
        return results
```

### 4. 集成到现有系统

修改 `src/ai_integration.py`：

```python
from .local_ai_client import LocalAIClient

class AIClient:
    def __init__(self, provider="auto", model_path=None, **kwargs):
        self.provider = provider
        if provider == "local" and model_path:
            self.local_client = LocalAIClient(model_path)
        else:
            # 原有的其他AI客户端逻辑
            pass
    
    def classify_sentiment(self, texts: List[str]) -> List[float]:
        if self.provider == "local":
            return self.local_client.classify_sentiment(texts)
        else:
            # 原有的其他AI客户端逻辑
            pass
```

### 5. 性能优化建议

#### GPU加速
```python
# 如果使用GPU
import torch
if torch.cuda.is_available():
    model = model.cuda()
    # 使用混合精度
    from torch.cuda.amp import autocast
```

#### 批处理优化
```python
def batch_classify(self, texts: List[str], batch_size: int = 16):
    """批量处理文本，提高效率"""
    results = []
    for i in range(0, len(texts), batch_size):
        batch = texts[i:i+batch_size]
        batch_results = self.classify_sentiment(batch)
        results.extend(batch_results)
    return results
```

### 6. 模型管理

#### 模型版本控制
```bash
# 使用Git LFS管理大文件
git lfs track "*.bin"
git lfs track "*.safetensors"
```

#### 模型更新
```python
def update_model(self, new_model_path: str):
    """更新模型"""
    self.tokenizer = AutoTokenizer.from_pretrained(new_model_path)
    self.model = AutoModelForSequenceClassification.from_pretrained(new_model_path)
    self.model.to(self.device)
```

## 部署检查清单

- [ ] 模型下载完成
- [ ] 配置文件更新
- [ ] 本地AI客户端实现
- [ ] 集成到现有系统
- [ ] 性能测试
- [ ] 错误处理机制
- [ ] 日志记录
- [ ] 模型版本管理

## 注意事项

1. **内存要求**: FinBERT需要约2GB内存
2. **存储空间**: 模型文件约400MB
3. **推理速度**: CPU推理较慢，建议使用GPU
4. **中文支持**: 确保模型支持中文文本
5. **错误处理**: 添加模型加载失败的备用方案

## 测试命令

```bash
# 测试模型加载
python -c "from src.ai.local_ai_client import LocalAIClient; client = LocalAIClient('models/finbert/finbert-tone'); print('模型加载成功')"

# 测试情绪分析
python -c "from src.ai.local_ai_client import LocalAIClient; client = LocalAIClient('models/finbert/finbert-tone'); result = client.classify_sentiment(['股票市场表现良好']); print(f'情绪得分: {result[0]}')"
```
