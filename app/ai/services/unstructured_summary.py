#unstructured_summary.py

import json
import numpy as np
import uuid
import yfinance as yf
from dotenv import load_dotenv
from tqdm import tqdm
from sklearn.metrics.pairwise import cosine_similarity
from sklearn.decomposition import TruncatedSVD
from transformers import AutoTokenizer, AutoModel
import torch
import os
from openai import OpenAI
from dateutil import parser 
import pymysql
import joblib
import pandas as pd
from datetime import datetime, timedelta
from dateutil import parser
from app.ai.services.brent_data_pipeline import build_full_dataset
# from app.ai.services.card2 import generate_card_news  

load_dotenv()

# CrudeBERT 모델 로드
def load_crudebert():
    tokenizer = AutoTokenizer.from_pretrained("bert-base-uncased")
    model = AutoModel.from_pretrained("Captain-1337/CrudeBERT")
    model.eval()
    device = "cuda" if torch.cuda.is_available() else "cpu"
    model.to(device)
    return tokenizer, model, device

# 임베딩 함수
def crudebert_embedding(text, tokenizer, model, device):
    inputs = tokenizer(
        text,
        return_tensors="pt",
        truncation=True,
        padding=True,
        max_length=512
    ).to(device)
    with torch.no_grad():
        outputs = model(**inputs)
    # CLS 토큰 임베딩
    emb = outputs.last_hidden_state[:, 0, :].cpu().numpy()[0]
    return emb

# 데이터 로드
def load_from_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)
def load_from_db(conn):
    cursor = conn.cursor(pymysql.cursors.DictCursor)
    cursor.execute("SELECT * FROM oil_news")
    return cursor.fetchall()

# 중복 제거(제목)
def remove_duplicate_titles(news_data):
    unique_titles = set()
    filtered = []
    for item in news_data:
        title = item.get("title", "").strip()
        if title and title not in unique_titles:
            unique_titles.add(title)
            filtered.append(item)
    print(f"중복 제거 후 {len(filtered)}개 문서 남음")
    return filtered

# 내용 임베딩
def embed_all_documents(filtered_news, tokenizer, model, device):
    texts = [
        (item.get("title", "") + " " + item.get("text", "")).strip()
        for item in filtered_news
    ]
    embeddings = []
    print("임베딩 생성 중 (CrudeBERT) ...")
    for t in tqdm(texts):
        emb = crudebert_embedding(t, tokenizer, model, device)
        embeddings.append(emb)
    embeddings = np.array(embeddings)
    print(f"임베딩 완료: {embeddings.shape}")
    return embeddings

# 유사도 비교 그룹핑
def build_groups(filtered_news, embeddings, threshold=0.85):
    sim_matrix = cosine_similarity(embeddings)
    groups = []
    visited = set()
    for i in range(len(filtered_news)):
        if i in visited:
            continue
        group = [i]
        visited.add(i)
        for j in range(i + 1, len(filtered_news)):
            if sim_matrix[i, j] >= threshold:
                group.append(j)
                visited.add(j)
        groups.append(group)
    print(f"총 {len(groups)}개 그룹 생성됨")
    return groups, sim_matrix

# +UUID
def build_unique_news(filtered_news, groups):
    result = []
    for group in groups:
        rep_idx = max(group, key=lambda idx: len(filtered_news[idx].get("text", "")))
        rep_doc = filtered_news[rep_idx].copy()
        rep_doc["event_uuid"] = str(uuid.uuid4())
        rep_doc["group_size"] = len(group)
        result.append(rep_doc)
    return result

def parse_date(raw_date: str):
    return parser.parse(raw_date)

def get_published_date(article: dict):
    if "published" in article:
        return article["published"]
    if "published_date" in article:
        return article["published_date"]
    return None

def get_brent_prices(event_date_str):
    event_date = datetime.strptime(event_date_str, "%Y-%m-%d")

    start = (event_date - timedelta(days=3)).strftime("%Y-%m-%d")
    end   = (event_date + timedelta(days=3)).strftime("%Y-%m-%d")


    df = yf.download("BZ=F", start=start, end=end)

    if df.empty:
        print("⚠ Yahoo Finance 데이터 없음")
        return None

    df.index = pd.to_datetime(df.index)

    prev_day = event_date - timedelta(days=1)

    def get_close(date):
        if date in df.index:
            return float(df.loc[date]["Close"])
        else:
            valid_days = df.index[df.index <= date]
            if len(valid_days):
                return float(df.loc[valid_days[-1]]["Close"])
            return None

    prev_close = get_close(prev_day)
    event_close = get_close(event_date)

    # 변동률 계산
    if prev_close and event_close:
        pct_change = ((event_close - prev_close) / prev_close) * 100
    else:
        pct_change = None

    return {
        "event_date": event_date_str,
        "prev_close": prev_close,
        "event_close": event_close,
        "pct_change": pct_change
    }

def attach_brent_price_info(articles):
    for article in articles:
        raw_date = get_published_date(article)

        if raw_date is None:
            article["brent_price"] = None
            continue

        try:
            event_dt = parse_date(raw_date)
            event_date_str = event_dt.strftime("%Y-%m-%d")

            brent_info = get_brent_prices(event_date_str)

            article["brent_price"] = brent_info

        except Exception as e:
            article["brent_price"] = None
            print(f"⚠ Brent 가격 조회 실패 ({article.get('title','')[:30]}): {e}")

    return articles

# summary 생성
def create_client(api_key):
    client = OpenAI(api_key=api_key)
    return client
brent_oil_categories = [
    "국제 유가 동향",
    "산유국 정책",
    "공급망 및 원유 생산",
    "수요 및 소비 동향",
    "지정학 및 국제 분쟁",
    "정책, 규제, 에너지 전환",
    "금융, 투자, 환율",
    "기업, 시장 전략",
    "ESG, 환경, 기후",
]
def analyze_article(article_data: dict, client):
    title = article_data.get('title', '')
    url = article_data.get('url', '')
    published = article_data.get('published') or article_data.get('published_date', '')
    content = article_data.get('content', '').strip()
    group_size = article_data.get('group_size', 1)
    event_uuid = article_data.get('event_uuid', None)

    if not content:
        return {
            "title": title,
            "url": url,
            "published": published,
            "category": "기타",
            "content": content,
            "group_size": group_size,
            "event_uuid": event_uuid,
            "summary": None,
            "sentiment": None,
            "trust": None,
            "relation_nation": []
        }
    
    raw_date = get_published_date(article_data)
    event_dt = parse_date(raw_date)
    event_date_str = event_dt.strftime("%Y-%m-%d")

    brent_info = get_brent_prices(event_date_str)

    if brent_info:
        prev_close = brent_info.get("prev_close")
        event_close = brent_info.get("event_close")

        if prev_close and event_close:
            daily_change_pct = ((event_close - prev_close) / prev_close) * 100
        else:
            daily_change_pct = None
    else:
        daily_change_pct = None

    daily_change_pct = brent_info.get("pct_change")  

    content_sample = content[:3000] if len(content) > 3000 else content
    prompt = f"""
당신은 국제 Brent Oil 관련 뉴스를 분석하는 전문가입니다.
아래 기사를 분석하여 반드시 JSON 형식으로만 출력하세요.
절대 규칙:
1. JSON 형식으로만 출력 (설명문, 해석문, 마크다운 금지)
2. 모든 필드는 필수이며 비워두면 안 됨
3. 기사 내용이 불충분해도 추론을 통해 최소 정보 포함
---
기사 정보:
제목: {title}
발행일: {published}
본문: {content_sample}
---
분석 항목:
1. 요약 (summary)
    - 한국어로 3~5문장
    - 기사 제목처럼 핵심 주장·결과·시사점을 압축적으로 작성
    - '무엇을 발견했다 / 어떻게 전망했다 / 어떤 변화가 나타났다' 중심으로 기술
    - 자극적이되 과장하지 않고, 사실 기반으로 임팩트 있게 표현
    - 구체적 수치(성장률, 증감률 등)와 기관명(OECD, Deloitte, IMF 등)을 포함
    - 일반 설명이 아닌, 헤드라인처럼 바로 눈에 들어오는 요약
2. 감성 분석 (sentiment)
    - explanation: 1~2문장 설명
    - score: -1.0~1.0 (0.1 단위)
    - 감성 분류를 할 때는 정확한 기준으로 감성 점수는 -1.0~1.0 범위의 실수, 반드시 0.1 단위로 세분화해서 점수를 매겨.
    - 매우 긍정적일수록 1.0, 매우 부정적일수록 -1.0에 가까워져.
    - 긍정적 요인은 국제 유가 상승, 공급 제한, 경제 회복, 투자 확대 등이 있어.
    + 1.0 (극단적 긍정) OPEC+ 대규모 감산, 유가 급등, 글로벌 수요 폭증
    + 0.9 (매우 긍정) 감산 연장, 지정학적 리스크로 상승세
    + 0.8 (강한 긍정) 재고 감소, 달러 약세, 경제 회복
    + 0.7 (뚜렷한 긍정) 유가 상승세 지속
    + 0.6 (명확한 긍정) 수요 증가, 투자 확대
    + 0.5 (보통 긍정) 공급 안정, 완만한 상승
    + 0.4 (약한 긍정) 긍정적 분위기, 점진적 개선
    + 0.3 (온건 긍정) 유가 안정세 유지
    + 0.2 (미세한 긍정) 소폭 회복
    + 0.1 (거의 중립) 뚜렷한 이슈 없음, 완만한 개선 조짐
    0.0 (극단적 부정) 긍정, 부정 모두 없음
    -0.1 (거의 중립) 불확실성, 소폭 둔화
    -0.2 (미세한 부정) 공급 증가, 재고 확대
    -0.3 (온건 부정) 수요 둔화, 공급 불안
    -0.4 (약한 부정) 유가 하락세 지속
    -0.5 (보통 부정) 공급 과잉, 감산 무효화
    -0.6 (명확한 부정) 수출 감소, 재정 악화
    -0.7 (뚜렷한 부정) 경기 침체, 수익성 악화
    -0.8 (강한 부정) 구조적 공급 과잉
    -0.9 (매우 부정) OPEC 협의 실패, 대규모 손실
    -1.0 (극단적 부정) 유가 폭락, 시장 붕괴
    - 감정이 혼재된 경우, 긍/부정 요인을 종합하여 근사값을 산출해.
    - 만약 명확한 방향성이 없거나 긍·부정이 혼재된 경우, 0을 기준으로 근접한 쪽으로 판단해.
    - `explanation`에는 이유를 1~2문장으로 기술해.

    전일 대비 Brent 가격 변화율 참고치
    전일 대비 변화율: {daily_change_pct}%

    - 변화율이 양수면 감성 점수를 조금(+0.1~+0.3 범위) 상향 보정
    - 변화율이 음수면 감성 점수를 조금(-0.1~-0.3 범위) 하향 보정
    - 변화율의 절대값이 클수록 조정폭도 커진다.

    최종 점수는 하나만 출력해야 한다.
    - 기사 기반 점수와 가격 변동률 조정값을 합산하여 하나의 최종 score를 출력하라.
    - score는 반드시 -1.0~+1.0 사이의 실수여야 한다.

3. 카테고리 (category)
    - 브렌트유 산업 관련 뉴스 카테고리 리스트에서 정확히 1개만 선택해.
    - 반드시 카테고리 리스트에 있는 카테고리만 선택해야해.
    카테고리: {", ".join(brent_oil_categories)}
4. 신뢰도 평가 (trust)
    - explanation: 1~2문장 설명
    - score: 0.0~1.0 (0.1 단위)
    - reliable: true(0.5 이상) / false(0.5 미만)
    LLM이 생성한 요약과 원문 간의 내용 불일치,
    또는 논리적 비약은 모두 신뢰도 감점 요인이야.
    - 신뢰도 점수는 0.0~1.0 사이 0.1 단위로 부여해.
    - “공식 기관, 기업 발표, 정부 보도자료, 수치 데이터”가 포함되면 신뢰도 상승.
    - “비공식 인터뷰, 익명 관계자, 보도 전언”이 포함되면 신뢰도 하락.
    -출력은 반드시 JSON 형식으로, 아래 구조로만 출력해.
    1.0 (매우 신뢰)  정부/기업 공식 발표, 수치 기반 기사
    0.9 (신뢰) 공식 보도자료 중심, 명확한 근거 포함
    0.8 (다소 신뢰) 사실 중심이지만 일부 해석 포함
    0.7 (보통) 기자 견해 일부 포함, 단편적 사실 인용
    0.6 (불확실) 의견/전망 비중이 높은 기사
    0.5 (중립) 사실과 추측이 혼재됨
    0.4 (낮은) 신뢰 익명 관계자 인용 중심
    0.3 (매우 낮음) 추측성 기사, 불명확한 근거
    0.2 (신뢰 불가) 사실 불일치 가능성 있음
    0.1 (거짓) 가능성과장/환각, 표현 존재
    0.0 (명백히 거짓) 기사 내용과 불일치하거나 허위 정보
    - 신뢰도가 0.5 이상이면 `true`,
    0.5 미만이면 `false`로 설정하라.
    - `explanation`에는 이유를 1~2문장으로 기술해.
5. 국가 관련성 (relation_nation)
    - 본문에서 언급된 지명, 기업 국적, 기관, 인물 등을 기반으로 가장 관련이 깊은 주요 국가를 1개 또는 2개까지 추출해.
    - 본문에서 직접 언급되지 않더라도, 기사 맥락상 가장 관련이 깊은 국가를 반드시 최소 1개 이상 포함시켜라.
    - 각 국가는 반드시 영어 이름과 ISO 3166-1 alpha-3 코드를 함께 제공해야 해.
    - 판단 기준:
    기사 주체 기업의 본사가 위치한 나라
    정부나 규제 기관이 포함된 경우 그 국가
    지정학적 갈등 또는 원유 공급 관련 주요국
    명시적 언급이 없을 경우, 기사 주제에 따라 추론하라.
    - 기사와 가장 관련 깊은 국가 1~2개
    - 맥락상 추론 가능하면 포함
    - 출력 형식: 각 국가는 name(영어 정식 국가명)과 code(ISO 3166-1 alpha-3) 객체로 구성
    - 예시:
      [
        {{"name": "United States", "code": "USA"}},
        {{"name": "Saudi Arabia", "code": "SAU"}}
      ]
---
출력 형식 (이 구조로만):
{{
  "summary": "한국어 요약 (최소 2문장)",
  "sentiment": {{
    "explanation": "감성 판단 근거"
    "score": 0.0
  }},
  "category": "카테고리명",
  "trust": {{
    "explanation": "신뢰도 판단 근거"
    "score": 0.0,
    "reliable": true,
  }},
  "relation_nation": [
    {{"name": "Country Name", "code": "XXX"}},
    {{"name": "Country Name 2", "code": "YYY"}}
  ],
  "daily_change_pct": 0.0
}}
"""
    try:
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
            response_format={"type": "json_object"}
        )
        analysis = json.loads(response.choices[0].message.content)

        # 안전성 보정 처리
        summary = analysis.get("summary", "") or "요약 정보 없음"
        sentiment = analysis.get("sentiment", {"score": 0.5, "explanation": ""})
        trust = analysis.get("trust", {"score": 0.5, "explanation": "", "reliable": True})
        relation = analysis.get("relation_nation", ["미국"])
        return {
            "title": title,
            "url": url,
            "published": published,
            "category": analysis.get("category", "기타"),
            "content": content,
            "group_size": group_size,
            "event_uuid": event_uuid,
            "summary": analysis.get("summary", ""),
            "sentiment": analysis.get("sentiment", {"explanation": "", "score": 0.5}),
            "trust": analysis.get("trust", {"explanation": "", "score": 0.5, "reliable": True}),
            "relation_nation": analysis.get("relation_nation", []),
            "daily_change_pct": daily_change_pct
        }
        if not result["summary"] or result["summary"] == "":
            result["summary"] = "요약 정보 없음"
        if not result["relation_nation"] or len(result["relation_nation"]) == 0:
            result["relation_nation"] = [{"name": "United States", "code": "USA"}]
        else:
            # 각 국가 객체가 name과 code를 모두 가지고 있는지 검증
            validated_nations = []
            for nation in result["relation_nation"]:
                if isinstance(nation, dict) and "name" in nation and "code" in nation:
                    validated_nations.append(nation)
            if not validated_nations:
                result["relation_nation"] = [{"name": "United States", "code": "USA"}]
            else:
                result["relation_nation"] = validated_nations
        if not isinstance(result.get("sentiment"), dict):
            result["sentiment"] = {
                "explanation": "감성 분석 정보를 제대로 받지 못해 기본값을 사용함.",
                "score": 0.5
            }
        else:
            score = result["sentiment"].get("score", 0.5)
            explanation = result["sentiment"].get("explanation", "")
            if not explanation:
                explanation = "기사의 전반적인 톤과 내용을 기반으로 산출한 감성 점수임."
            result["sentiment"] = {
                "explanation": explanation,
                "score": score
            }
        if not isinstance(result["trust"], dict):
            result["trust"] = {"score": 0.5, "reliable": True, "explanation": ""}
        else:
            if "score" not in result["trust"]:
                result["trust"]["score"] = 0.5
            if "reliable" not in result["trust"]:
                result["trust"]["reliable"] = result["trust"]["score"] >= 0.5
            if "explanation" not in result["trust"]:
                result["trust"]["explanation"] = ""
        return result
    except Exception as e:
        print(f":경고: 분석 오류 ({title[:40]}): {e}")
        return {
            "title": title,
            "url": url,
            "published": published,
            "category": "기타",
            "content": content,
            "group_size": group_size,
            "event_uuid": event_uuid,
            "summary": None,
            "sentiment": None,
            "trust": None,
            "relation_nation": []
        }
    

def analyze_all_articles(articles, client, tqdm_desc="기사 분석 중"):
    results = []
    count_new = 0
    for item in tqdm(articles, desc=tqdm_desc):
        summary = item.get("summary")
        # summary가 없으면 분석
        if summary in [None, "", "null", "요약 정보 없음"]:
            analyzed = analyze_article(item, client)
            results.append(analyzed)
            count_new += 1
        else:
            results.append(item)
    return results, count_new

# 임베딩 관련 함수들
def get_embedding(text, tokenizer, model, max_length=512):
    inputs = tokenizer(
        text,
        return_tensors="pt",
        padding=True,
        truncation=True,
        max_length=max_length
    )
    with torch.no_grad():
        outputs = model(**inputs)
        embedding = outputs.last_hidden_state[:, 0, :].numpy()  # 768차원
    return embedding[0]

# 차원 축소 설정
input_dim = 768
target_dim = 64
np.random.seed(42)
projection_matrix = np.random.randn(input_dim, target_dim)  # (768, 64)

def reduce_to_64dim(vec768):
    return np.dot(vec768, projection_matrix)

def generate_summary_embeddings(
    articles,
    tokenizer,
    model,
    output_file,
    umap_path=r"app\ai\repository\structured_params\model_weight\umap_64to20.model",
    kmeans_path=r"app\ai\repository\structured_params\model_weight\kmeans_20d_30clusters.model",
):
    embeddings_768 = []
    valid_indices = []
    generated_count = 0
    # --------------------------
    # 1차: summary 있는 row는 즉시 768 → 랜덤 64차원 변환
    # --------------------------
    for i, article in enumerate(tqdm(articles, desc="1차 변환")):
        summary = article.get("summary", None)
        if not summary:
            article["summary_embedding"] = None
            continue
        try:
            emb768 = get_embedding(summary, tokenizer, model)  # 768차원
            emb64 = reduce_to_64dim(emb768)                    # 64차원 변환
            article["summary_embedding"] = emb64.tolist()
            generated_count += 1
        except Exception as e:
            print(f":경고: 임베딩 실패: article {i} — {e}")
            article["summary_embedding"] = None
    # --------------------------
    # 2차: 64차원이 아니거나 None → SVD 재처리 대상으로 모음
    # --------------------------
    for i, article in enumerate(tqdm(articles, desc="검증 및 SVD 준비")):
        emb = article.get("summary_embedding", None)
        if (
            emb in [None, "null", []]
            or not isinstance(emb, list)
            or len(emb) != target_dim
        ):
            try:
                new768 = get_embedding(article["summary"], tokenizer, model)
                embeddings_768.append(new768)
                valid_indices.append(i)
            except Exception:
                article["summary_embedding"] = None
    # --------------------------
    # 3차: SVD로 강제 64차원 맞추기
    # --------------------------
    if len(embeddings_768) > 0:
        print("\n:불: TruncatedSVD를 이용한 강제 차원 축소 수행")
        arr = np.array(embeddings_768)
        svd = TruncatedSVD(n_components=target_dim, random_state=42)
        reduced = svd.fit_transform(arr)
        print(f"설명된 분산 비율: {svd.explained_variance_ratio_.sum():.4f}")
        for idx, row_idx in enumerate(valid_indices):
            articles[row_idx]["summary_embedding"] = reduced[idx].tolist()
            generated_count += 1
    # --------------------------
    # 4차: UMAP + KMeans → cluster_id만 저장
    # --------------------------
    emb_list = []
    idx_list = []
    for i, article in enumerate(articles):
        emb = article.get("summary_embedding")
        if isinstance(emb, list) and len(emb) == target_dim:
            emb_list.append(np.array(emb, dtype=float))
            idx_list.append(i)
    if emb_list:
        # UMAP, KMeans 모델 로드
        umap_model = joblib.load(umap_path)
        kmeans = joblib.load(kmeans_path)
        print("====================================")
        print("[DEBUG] UMAP PATH:", umap_path) 
        print("[DEBUG] KMEANS PATH:", kmeans_path)
        print("[DEBUG] UMAP MODEL LOADED:", type(umap_model))
        print("[DEBUG] KMEANS MODEL LOADED:", type(kmeans))
        print("====================================")
        emb_arr = np.vstack(emb_list)          # (N, 64)
        emb_20d = umap_model.transform(emb_arr)  # (N, 20)
        km_labels = kmeans.predict(emb_20d)
        # 각 기사 dict에 cluster_id만 부여
        for j, art_idx in enumerate(idx_list):
            articles[art_idx]["cluster_id"] = int(km_labels[j])
    else:
        # 임베딩이 없다면 -1로 채움
        for art in articles:
            articles["cluster_id"] = -1
    # --------------------------
    # 5차: 파일(JSON) 저장
    # --------------------------
    if output_file:
        os.makedirs(os.path.dirname(output_file), exist_ok=True)
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(articles, f, ensure_ascii=False, indent=2)
        print(f"\n 결과 저장 완료: {output_file}")
    return articles, generated_count



def daily_news_data(news_data):

    # 2) 중복 제거
    filtered = remove_duplicate_titles(news_data)

    # 3) CrudeBERT 로드
    tokenizer, model, device = load_crudebert()

    # 4) 본문 임베딩 (내용 + 제목)
    embeddings = embed_all_documents(filtered, tokenizer, model, device)

    # 5) 유사도 기반 그룹 생성
    groups, sim_matrix = build_groups(filtered, embeddings)

    # 6) 그룹 대표 문서 + UUID 부여
    grouped_news = build_unique_news(filtered, groups)

    api_key = os.getenv("OPENAI_API_KEY")

    client = create_client(api_key)

    # 8) summary / sentiment / trust 생성
    analyzed_news, new_count = analyze_all_articles(grouped_news, client)
    print(f"새로 생성된 summary 개수: {new_count}")

    # 9) summary embedding 생성 (768→64)
    output_emb_file = "data/embedded_news.json"
    final_articles, embed_count = generate_summary_embeddings(
        analyzed_news,
        tokenizer,
        model,
        output_emb_file
    )
    # 10) 정형 데이터 + 클러스터링 통합
    df_final, news_clusters= build_full_dataset(
        final_articles,
        start="2013-09-01",
        end=None,
        target_horizon=5,
        max_cluster=30
    )
    for i, art in enumerate(final_articles):
        art["cluster_km"] = int(news_clusters.iloc[i]["cluster_km"])

    
    # os.makedirs("images", exist_ok=True)

    # for idx, article in enumerate(final_articles):
    #     summary = article.get("summary")
    #     if not summary:
    #         continue
    #     save_path = f"repository/data/images/card_{idx}.jpg"
    #     generate_card_news(summary, save_path)
    #     print(f"[{idx}] 카드뉴스 생성 완료 → {save_path}")
        
    # print("\n:짠: 모든 카드뉴스 생성 완료!")

    return final_articles