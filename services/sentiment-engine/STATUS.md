# Sentiment Engine Service

**Status:** 🔜 **PLANNED** (Phase 6 - Q3 2025)

## Purpose
Analyze sentiment of financial news articles using NLP to provide contextual insights for buy/sell recommendations.

## Planned Implementation

### Architecture
- **Processing Engine:** Celery workers (one per Pi node)
- **NLP Models:** VADER + FinBERT (financial domain-specific)
- **Orchestration:** Triggered by news-fetcher service
- **Storage:** Updates `news_articles.sentiment_*` columns

### Sentiment Analysis Pipeline

```
News Article
    ↓
1. Text Preprocessing
   - Remove HTML/markdown
   - Lowercase, tokenize
   - Remove stop words
    ↓
2. VADER Sentiment (baseline)
   - Rule-based lexicon
   - Fast but simple
    ↓
3. FinBERT Sentiment (advanced)
   - Transformer model trained on financial text
   - Slower but more accurate
    ↓
4. Ensemble Score
   - Weighted average of VADER + FinBERT
   - VADER weight: 30%
   - FinBERT weight: 70%
    ↓
5. Save to Database
   - sentiment_score: -1.00 to +1.00
   - sentiment_label: positive/neutral/negative
   - sentiment_confidence: 0.00 to 1.00
```

### Models

#### 1. VADER (Valence Aware Dictionary and sEntiment Reasoner)
```python
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

analyzer = SentimentIntensityAnalyzer()

def analyze_vader(text: str) -> dict:
    """
    Returns:
        {
            'compound': -0.7351,  # Overall score (-1 to +1)
            'pos': 0.000,
            'neu': 0.254,
            'neg': 0.746
        }
    """
    scores = analyzer.polarity_scores(text)
    return scores
```

**Pros:**
- Very fast (<1ms per article)
- No GPU required
- Good baseline for financial text

**Cons:**
- Rule-based, limited context understanding
- Doesn't handle sarcasm or complex sentiment

#### 2. FinBERT (Financial BERT)
```python
from transformers import AutoTokenizer, AutoModelForSequenceClassification
import torch

# Load pre-trained model
tokenizer = AutoTokenizer.from_pretrained("ProsusAI/finbert")
model = AutoModelForSequenceClassification.from_pretrained("ProsusAI/finbert")

def analyze_finbert(text: str) -> dict:
    """
    Returns:
        {
            'label': 'positive',  # positive, negative, neutral
            'score': 0.9342,       # Confidence 0-1
            'logits': [...]
        }
    """
    # Tokenize
    inputs = tokenizer(text, return_tensors="pt", truncation=True, max_length=512)

    # Inference
    with torch.no_grad():
        outputs = model(**inputs)

    # Get probabilities
    probs = torch.nn.functional.softmax(outputs.logits, dim=-1)
    label_id = torch.argmax(probs)
    score = probs[0][label_id].item()

    labels = ['positive', 'negative', 'neutral']
    return {
        'label': labels[label_id],
        'score': score,
        'probs': probs[0].tolist()
    }
```

**Pros:**
- State-of-the-art accuracy for financial text
- Understands context and nuance
- Pre-trained on 10K+ financial documents

**Cons:**
- Slower (~100ms per article on CPU)
- Requires more memory (500MB model)
- May need GPU for high throughput (future enhancement)

### Ensemble Strategy

```python
def calculate_ensemble_sentiment(text: str) -> dict:
    """Combine VADER and FinBERT for robust sentiment"""

    # Get both scores
    vader_result = analyze_vader(text)
    finbert_result = analyze_finbert(text)

    # Convert FinBERT label to score
    finbert_score = {
        'positive': +1.0,
        'neutral': 0.0,
        'negative': -1.0
    }[finbert_result['label']]

    # Weighted ensemble
    vader_weight = 0.30
    finbert_weight = 0.70

    ensemble_score = (
        vader_weight * vader_result['compound'] +
        finbert_weight * finbert_score
    )

    # Determine label
    if ensemble_score > 0.25:
        label = 'positive'
    elif ensemble_score < -0.25:
        label = 'negative'
    else:
        label = 'neutral'

    # Confidence is FinBERT's confidence
    confidence = finbert_result['score']

    return {
        'score': round(ensemble_score, 2),
        'label': label,
        'confidence': round(confidence, 2),
        'breakdown': {
            'vader': vader_result['compound'],
            'finbert': finbert_score,
            'finbert_confidence': finbert_result['score']
        }
    }
```

### Celery Task

```python
# src/tasks.py
from celery import Celery

app = Celery('sentiment_engine', broker='redis://redis:6379/0')

@app.task
def analyze_article_sentiment(article_id: int):
    """Analyze sentiment for a single article"""

    # Load article from database
    article = load_article(article_id)

    # Combine title + description + content
    text = f"{article.title}. {article.description} {article.content}"

    # Analyze sentiment
    result = calculate_ensemble_sentiment(text)

    # Update database
    update_article_sentiment(
        article_id=article_id,
        score=result['score'],
        label=result['label'],
        confidence=result['confidence']
    )

    return result

@app.task
def analyze_batch(article_ids: list[int]):
    """Analyze sentiment for multiple articles"""
    return group(analyze_article_sentiment.s(aid) for aid in article_ids)()
```

### Performance Optimization

**For High Throughput:**
```python
# Use batch inference for FinBERT
def analyze_finbert_batch(texts: list[str]) -> list[dict]:
    """Process multiple articles at once"""
    inputs = tokenizer(
        texts,
        return_tensors="pt",
        truncation=True,
        padding=True,
        max_length=512
    )

    with torch.no_grad():
        outputs = model(**inputs)

    probs = torch.nn.functional.softmax(outputs.logits, dim=-1)

    results = []
    for i in range(len(texts)):
        label_id = torch.argmax(probs[i])
        results.append({
            'label': labels[label_id],
            'score': probs[i][label_id].item()
        })

    return results
```

**For Low Latency:**
```python
# Use ONNX Runtime for 2-3x speedup
from optimum.onnxruntime import ORTModelForSequenceClassification

model = ORTModelForSequenceClassification.from_pretrained(
    "ProsusAI/finbert",
    export=True
)
# Inference is 2-3x faster
```

## Dependencies
**Prerequisites:**
- ✅ news-fetcher service (provides articles)
- ⏳ Redis (Celery broker)
- ⏳ Celery workers deployed

**Technology Stack:**
- Python 3.11+
- `transformers` (HuggingFace)
- `vaderSentiment`
- `torch` (CPU initially, GPU optional)
- `optimum` (ONNX optimization)
- Celery

**Model Storage:**
- FinBERT model: ~500MB (download on first run)
- Store in persistent volume (PVC) for fast startup

## Implementation Plan

### Step 1: VADER Baseline (Week 1)
- Implement VADER analyzer
- Create Celery tasks
- Test on sample articles

### Step 2: FinBERT Integration (Week 2)
- Load FinBERT model
- Implement inference pipeline
- Optimize for ARM64 (CPU-only initially)

### Step 3: Ensemble Logic (Week 3)
- Combine VADER + FinBERT
- Calibrate weights
- Validate against manually labeled examples

### Step 4: Celery Deployment (Week 4)
- Deploy to Kubernetes
- Configure 8 workers
- Test throughput

### Step 5: Integration (Week 5)
- Integrate with news-fetcher
- Automatic sentiment analysis on new articles
- Backfill sentiment for existing articles

### Step 6: Testing & Validation (Week 6)
- Manual validation (sample 100 articles)
- Accuracy measurement
- Performance benchmarking

## Performance Targets
- **Throughput:** 500 articles/minute (with 8 workers)
- **Latency:** <200ms per article (VADER + FinBERT)
- **Accuracy:** >80% agreement with human labelers
- **Memory:** <1GB per worker

## Monitoring
```sql
-- Sentiment distribution (last 7 days)
SELECT
    sentiment_label,
    COUNT(*) as articles,
    AVG(sentiment_confidence) as avg_confidence
FROM news_articles
WHERE published_at >= NOW() - INTERVAL '7 days'
  AND sentiment_score IS NOT NULL
GROUP BY sentiment_label;

-- Articles pending sentiment analysis
SELECT COUNT(*)
FROM news_articles
WHERE sentiment_score IS NULL
  AND fetched_at >= NOW() - INTERVAL '24 hours';

-- Average sentiment by ticker (last 30 days)
SELECT
    ticker,
    COUNT(*) as articles,
    AVG(sentiment_score) as avg_sentiment,
    STDDEV(sentiment_score) as sentiment_volatility
FROM news_articles,
     UNNEST(tickers) as ticker
WHERE published_at >= NOW() - INTERVAL '30 days'
  AND sentiment_score IS NOT NULL
GROUP BY ticker
HAVING COUNT(*) >= 5  -- At least 5 articles
ORDER BY avg_sentiment DESC
LIMIT 50;
```

## Timeline
- **Start Date:** After news-fetcher deployed
- **Duration:** 6 weeks
- **Go-Live:** Q3 2025

## Success Metrics
- [ ] 500 articles/minute throughput
- [ ] >80% accuracy vs human labels
- [ ] <200ms average latency
- [ ] Zero model crashes
- [ ] Comprehensive sentiment history

## Related Documentation
- [FinBERT Paper](https://arxiv.org/abs/1908.10063)
- [VADER Documentation](https://github.com/cjhutto/vaderSentiment)
- [HuggingFace Transformers](https://huggingface.co/docs/transformers)

## Future Enhancements (Phase 7+)
- Add GPU node for 10x speedup
- Fine-tune FinBERT on crypto/forex news
- Aspect-based sentiment (separate scores for different aspects)
- Sentiment trends over time (momentum indicators)
- Multi-language support (translate → analyze)

**Last Updated:** 2025-10-28
