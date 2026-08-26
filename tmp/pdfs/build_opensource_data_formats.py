from pathlib import Path
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, KeepTogether
from pypdf import PdfReader
import subprocess

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "output" / "pdf" / "오픈소스데이터형식.pdf"
OUT.parent.mkdir(parents=True, exist_ok=True)

font = Path(r"C:\Windows\Fonts\malgun.ttf")
font_bold = Path(r"C:\Windows\Fonts\malgunbd.ttf")
pdfmetrics.registerFont(TTFont("Korean", str(font)))
pdfmetrics.registerFont(TTFont("KoreanBold", str(font_bold)))

PAGE = landscape(A4)
NAVY = colors.HexColor("#17324D")
BLUE = colors.HexColor("#2878B5")
PALE = colors.HexColor("#EAF2F8")
LIGHT = colors.HexColor("#F5F7FA")
GRAY = colors.HexColor("#59636E")

styles = getSampleStyleSheet()
styles.add(ParagraphStyle(name="TitleK", fontName="KoreanBold", fontSize=24, leading=31, textColor=NAVY, alignment=TA_CENTER, spaceAfter=12))
styles.add(ParagraphStyle(name="SubK", fontName="Korean", fontSize=10.5, leading=16, textColor=GRAY, alignment=TA_CENTER, spaceAfter=20))
styles.add(ParagraphStyle(name="H1K", fontName="KoreanBold", fontSize=16, leading=21, textColor=NAVY, spaceBefore=7, spaceAfter=9))
styles.add(ParagraphStyle(name="H2K", fontName="KoreanBold", fontSize=12.5, leading=17, textColor=BLUE, spaceBefore=5, spaceAfter=6))
styles.add(ParagraphStyle(name="BodyK", fontName="Korean", fontSize=9.2, leading=14, textColor=colors.HexColor("#202830"), spaceAfter=5))
styles.add(ParagraphStyle(name="SmallK", fontName="Korean", fontSize=7.5, leading=10.2, textColor=colors.HexColor("#202830")))
styles.add(ParagraphStyle(name="TinyK", fontName="Korean", fontSize=6.5, leading=8.5, textColor=colors.HexColor("#202830")))
styles.add(ParagraphStyle(name="CodeK", fontName="Korean", fontSize=8.3, leading=11.5, leftIndent=6, rightIndent=6, borderColor=colors.HexColor("#CBD5E1"), borderWidth=.5, borderPadding=6, backColor=LIGHT, spaceAfter=7))

def P(text, style="BodyK"):
    return Paragraph(text, styles[style])

def table(rows, widths, header=True, tiny=False):
    converted = []
    for ri, row in enumerate(rows):
        converted.append([P(str(x), "TinyK" if tiny else "SmallK") for x in row])
    t = Table(converted, colWidths=widths, repeatRows=1 if header else 0, hAlign="LEFT")
    commands = [
        ("FONTNAME", (0,0), (-1,-1), "Korean"),
        ("VALIGN", (0,0), (-1,-1), "TOP"),
        ("GRID", (0,0), (-1,-1), .35, colors.HexColor("#BAC4CE")),
        ("LEFTPADDING", (0,0), (-1,-1), 3 if tiny else 4), ("RIGHTPADDING", (0,0), (-1,-1), 3 if tiny else 4),
        ("TOPPADDING", (0,0), (-1,-1), 2 if tiny else 4), ("BOTTOMPADDING", (0,0), (-1,-1), 2 if tiny else 4),
        ("ROWBACKGROUNDS", (0,1), (-1,-1), [colors.white, LIGHT]),
    ]
    if header:
        commands += [("BACKGROUND", (0,0), (-1,0), NAVY), ("TEXTCOLOR", (0,0), (-1,0), colors.white), ("FONTNAME", (0,0), (-1,0), "KoreanBold")]
    t.setStyle(TableStyle(commands))
    return t

def header_footer(canvas, doc):
    canvas.saveState()
    w, h = PAGE
    canvas.setStrokeColor(colors.HexColor("#D6DEE6")); canvas.line(14*mm, 12*mm, w-14*mm, 12*mm)
    canvas.setFont("Korean", 7.5); canvas.setFillColor(GRAY)
    canvas.drawString(14*mm, 7.5*mm, "오픈소스 퀀트 프로젝트 공통·전용 데이터 형식")
    canvas.drawRightString(w-14*mm, 7.5*mm, f"{doc.page}")
    canvas.restoreState()

story = []
story += [Spacer(1, 18*mm), P("오픈소스 퀀트 프로젝트<br/>공통·전용 데이터 형식 보고서", "TitleK"),
          P("Backtrader · Zipline Reloaded · QuantConnect LEAN · Freqtrade · FinRL · Backtesting.py<br/>vn.py · QSTrader · PyAlgoTrade · PyPortfolioOpt · pysystemtrade · Lumibot", "SubK"),
          Spacer(1, 6*mm), P("목적", "H1K"),
          P("12개 오픈소스에서 요구하거나 실무적으로 권장되는 데이터를 공통 카테고리로 통합하고, 각 프로젝트에만 필요한 별도 입력 형식을 구분한다. 공통 시장 데이터마트를 먼저 구축한 후 프로젝트별 어댑터를 추가할 수 있도록 설계했다."),
          P("핵심 결론", "H1K"),
          P("모든 프로젝트가 동일하게 OHLCV 전체를 요구하는 것은 아니다. 백테스트·실거래 엔진은 OHLCV와 체결조건이 중심이고, PyPortfolioOpt는 가격행렬 또는 기대수익률·공분산이 핵심이다. pysystemtrade는 선물 롤·캐리·환율이, FinRL은 상태·행동·보상 및 특성이 별도로 필요하다."), PageBreak()]

story += [P("1. 통합 데이터 분류 체계", "H1K")]
cats = [
 ["분류", "주요 내용"], ["A. 식별자·시간", "종목, 거래소, 자산유형, 시각, 시간대, bar 주기"],
 ["B. 가격·거래량", "OHLCV, 수정주가, 거래대금, VWAP, 미결제약정"], ["C. 호가·체결", "Bid/Ask, 호가잔량, trade tick, quote tick"],
 ["D. 종목 마스터", "상장·폐지일, 통화, 승수, 호가단위, 거래시간"], ["E. 기업행동", "배당, 분할, 합병, 심볼 변경, 상장폐지"],
 ["F. 파생상품", "만기, 행사가, 콜·풋, 계약월, 롤, Greeks, funding"], ["G. 비용·규칙", "수수료, 스프레드, 슬리피지, 최소 주문량, 증거금"],
 ["H. 포트폴리오·리스크", "수익률, 벤치마크, 공분산, 무위험수익률, 포지션"], ["I. 특성·ML/RL", "기술지표, 거시변수, turbulence, 상태·행동·보상"],
 ["J. 실거래 상태", "주문, 체결, 포지션, 현금, 계좌잔고"]]
story += [table(cats, [42*mm, 206*mm]), Spacer(1, 5*mm), P("구분 기준: 필수=기본 실행에 직접 필요, 조건부=특정 자산·기능에 필요, 권장=신뢰성 있는 연구에 권장, 비핵심=일반 입력이 아님.", "SmallK")]

story += [P("2. 프로젝트별 데이터 카테고리 비교", "H1K")]
matrix = [
 ["프로젝트","A","B","C","D","E","F","G","H","I","J"],
 ["Backtrader","필수","필수","조건","권장","조건","조건","권장","권장","-","조건"],
 ["Zipline Reloaded","필수","필수","제한","필수","필수","선물","권장","권장","-","-"],
 ["QuantConnect LEAN","필수","필수","중요","필수","필수","조건","권장","권장","조건","조건"],
 ["Freqtrade","필수","필수","조건","필수","-","선물","필수","권장","FreqAI","필수"],
 ["FinRL","필수","필수","전략","권장","권장","전략","권장","필수","필수","조건"],
 ["Backtesting.py","필수","필수","제한","최소","직접","제한","권장","권장","-","-"],
 ["vn.py","필수","필수","중요","필수","자산","중요","필수","권장","조건","필수"],
 ["QSTrader","필수","가격","제한","권장","조정가","제한","권장","필수","-","-"],
 ["PyAlgoTrade","필수","필수","제한","최소","조정가","조건","권장","권장","-","제한"],
 ["PyPortfolioOpt","종목","가격/수익률","-","권장","반영","-","조건","필수","조건","-"],
 ["pysystemtrade","필수","가격","실거래","필수","-","핵심","필수","필수","-","실거래"],
 ["Lumibot","필수","필수","중요","필수","주식","중요","필수","권장","AI","실거래"],
]
story += [table(matrix, [36*mm]+[20.8*mm]*10, tiny=True), P("A~J는 앞 절의 통합 카테고리를 뜻한다. '조건'은 조건부, '-'는 비핵심이다.", "SmallK"), PageBreak()]

story += [P("3. 공통 데이터 표준", "H1K"), P("3.1 instrument_master", "H2K")]
master = [["필드","형식","구분","설명"],
 ["instrument_id","string","필수","변경되지 않는 내부 종목 ID"],["symbol","string","필수","티커 또는 거래쌍"],["exchange","string","필수","거래소"],
 ["asset_class","enum","필수","equity, crypto, forex, future, option"],["currency","string","필수","표시·결제 통화"],["timezone","string","필수","IANA 시간대"],
 ["listing_date / delisting_date","date","권장","상장 및 폐지 기간"],["price_tick / quantity_step","decimal","권장","호가·수량 증분"],
 ["minimum_quantity","decimal","권장","최소 주문수량"],["contract_multiplier","decimal","조건부","선물·옵션 승수"],["trading_calendar","string","권장","거래소 캘린더"],
 ["valid_from / valid_to","timestamp","권장","시점별 메타데이터 유효기간"]]
story += [table(master,[55*mm,35*mm,25*mm,133*mm]), P("단순 티커만 키로 사용하면 거래소별 중복과 심볼 변경을 처리하기 어렵다. 내부 instrument_id를 기본키로 사용한다.")]
story += [P("3.2 market_bar", "H2K"), P("instrument_id | timestamp | bar_start | bar_end | bar_interval | open | high | low | close | volume | turnover | open_interest | vwap | trade_count | adjusted_close | is_adjusted | session_type | data_source | received_at | quality_flag", "CodeK")]
rules = [["검증 항목","규칙"],["가격","high ≥ max(open, close), low ≤ min(open, close), high ≥ low"],["거래량","volume ≥ 0"],["중복","instrument_id + timestamp + bar_interval은 유일"],["시간","UTC 저장, 원 거래소 timezone 보존, bar 시작·종료 구분"],["완성상태","미완성 캔들과 완성 캔들 구분"],["조정","원시가격과 수정가격 및 조정 기준 구분"]]
story += [table(rules,[55*mm,193*mm])]
story += [P("3.3 asset_return 및 포트폴리오 입력", "H2K"), P("Long 형식: timestamp | instrument_id | simple_return | log_return | total_return. PyPortfolioOpt에는 종목별 가격행렬 또는 expected_return 벡터와 covariance matrix를 제공한다. 총수익률은 가격변화뿐 아니라 현금배당 등 분배금을 포함해야 한다."), PageBreak()]

story += [P("4. 공통 확장 테이블", "H1K")]
ext = [
 ["테이블","주요 필드","주요 적용 프로젝트"],
 ["quote_tick","instrument_id, timestamp, bid_price, bid_size, ask_price, ask_size, exchange, sequence_number","LEAN, vn.py, Freqtrade, Lumibot"],
 ["trade_tick","instrument_id, timestamp, trade_id, price, quantity, side, exchange, condition","LEAN, vn.py, Freqtrade order flow"],
 ["corporate_action","action_date, effective_timestamp, type, split_ratio, cash_amount, new_instrument_id","Zipline, LEAN, 주식형 엔진"],
 ["trading_rule","commission, maker/taker fee, spread, slippage, min qty/notional, tick, margin","전체 프로젝트의 현실적 평가"],
 ["derivative_contract","underlying, expiry, strike, right, multiplier, settlement, margin","LEAN, vn.py, pysystemtrade, Lumibot"],
 ["portfolio_state","cash, holdings, market_value, weight, realized/unrealized PnL","FinRL, QSTrader, 실거래 엔진"],
]
story += [table(ext,[40*mm,132*mm,76*mm])]

projects = [
 ("Backtrader", "최소: datetime, open, high, low, close, volume. 확장: openinterest, timeframe, compression 및 사용자 정의 data lines. 선물은 계약월·승수·롤 기준, 현금배당 전략은 배당·분할, 실거래는 주문·체결·포지션 응답을 추가한다."),
 ("Zipline Reloaded", "가격: sid, timestamp, OHLCV. 별도 필수: sid 기반 asset metadata(start/end/auto-close/exchange), 거래소 캘린더, split·dividend. 선물은 root symbol, 계약 심볼, 만기·notice·auto-close, tick size, multiplier가 필요하다."),
 ("QuantConnect LEAN", "TradeBar는 time+OHLCV, QuoteBar는 bid/ask 각각의 OHLC와 size, Tick은 체결 또는 호가 레코드다. 배당·분할·상장폐지·심볼 변경, 옵션/선물 chain, open interest를 별도 이벤트로 관리한다. bar 종료시점이 실제 이용 가능 시점이라는 원칙을 보존한다."),
 ("Freqtrade", "최소: date, open, high, low, close, volume. 거래쌍별 base/quote, 정밀도, 최소 주문금액, maker/taker fee가 필요하다. 무기한 선물은 mark·index·premium index·역사적 funding rate·open interest·증거금 규칙을 별도 관리한다."),
 ("FinRL", "원천: date, tic, OHLCV, adjusted_close. 특성: MACD, Bollinger, RSI, DX, 이동평균 등. RL 실험은 feature vector, cash, holdings, portfolio value, action, reward, next_state, done 및 turbulence/VIX를 명시해야 한다."),
 ("Backtesting.py", "DatetimeIndex와 대문자 Open, High, Low, Close가 기본이며 Volume은 선택이다. 추가 지표 열을 함께 전달할 수 있다. 기업행동·거래정지·스프레드·수수료는 프레임워크 밖에서 명시적으로 보정하는 편이 안전하다."),
 ("vn.py", "BarData: symbol, exchange, datetime, interval, volume, turnover, open_interest, OHLC. TickData: last price/volume, 누적 거래량·거래대금, 가격제한, 1~5단계 bid/ask 가격·잔량. ContractData와 Order/Trade/Position/Account 데이터도 실거래의 핵심이다."),
 ("QSTrader", "최소 가격은 timestamp, asset_id, close이며 전략에 따라 OHLCV·adjusted_close를 확장한다. cash, quantity, market value, weight, PnL의 포트폴리오 상태와 benchmark return, risk-free rate, commission·slippage가 중요하다."),
 ("PyAlgoTrade", "datetime, OHLCV, adjusted_close가 일반 bar 형식이다. frequency, adjusted-value 사용 여부, session close를 명시하고 수수료·슬리피지·거래량 기반 체결한도를 추가한다."),
 ("PyPortfolioOpt", "OHLC 전체가 필수는 아니다. 날짜×종목 가격행렬, 또는 기대수익률 벡터와 공분산행렬을 입력한다. CVaR/CDaR는 역사적 수익률 시나리오, Black-Litterman은 시가총액·벤치마크 비중·투자관점 P/Q/Omega가 추가된다."),
 ("pysystemtrade", "핵심은 선물 전용 구조다. 개별 계약 Final 가격, multiple prices(PRICE/CARRY/FORWARD와 각 계약 ID), adjusted continuous price, roll calendar, point size·통화·비용, spot FX가 필요하다. 일반 OHLCV만으로는 롤·캐리·실제 거래계약을 복원할 수 없다."),
 ("Lumibot", "Pandas 백테스트는 timezone-aware DatetimeIndex와 소문자 OHLCV를 사용한다. 주식은 dividend·stock_splits, 옵션은 expiry·strike·right·bid/ask·OI·IV·Greeks, 선물은 multiplier·settlement·roll·margin, 실거래는 주문·체결 상태가 필요하다."),
]
story += [PageBreak(), P("5. 프로젝트별 별도 데이터 형식", "H1K")]
for i,(name,desc) in enumerate(projects,1):
    story += [KeepTogether([P(f"5.{i} {name}", "H2K"), P(desc)])]

story += [PageBreak(), P("6. 프로젝트별 핵심 고유 데이터 요약", "H1K")]
unique = [["프로젝트","핵심 고유 데이터"]] + [[n, d] for n,d in [
 ("Backtrader","openinterest, 사용자 정의 data lines"),("Zipline Reloaded","sid, 자산 수명주기, 기업행동, 거래 캘린더"),("QuantConnect LEAN","TradeBar, QuoteBar, tick, Slice, 파생상품 chain"),
 ("Freqtrade","거래쌍 규칙, mark/index, funding, order flow"),("FinRL","상태·행동·보상, turbulence, 기술특성"),("Backtesting.py","대문자 OHLC(V) DataFrame"),
 ("vn.py","5단계 호가, turnover, OI, 계약·주문·계좌 객체"),("QSTrader","포트폴리오 상태, 벤치마크, 주문·체결 이벤트"),("PyAlgoTrade","adjusted close, bar frequency, session"),
 ("PyPortfolioOpt","기대수익률, 공분산, 수익률 시나리오, 시가총액"),("pysystemtrade","multiple prices, roll, carry/forward, FX"),("Lumibot","다중자산 Asset, 옵션 chain/Greeks, 주문 상태")]]
story += [table(unique,[50*mm,198*mm])]

story += [P("7. 권장 통합 데이터마트", "H1K")]
story += [P("01 instrument_master · 02 market_calendar · 03 market_bar · 04 trade_tick · 05 quote_tick · 06 corporate_action · 07 derivative_contract · 08 futures_roll_calendar · 09 futures_multiple_prices · 10 funding_rate · 11 fx_rate · 12 trading_cost_rule · 13 feature_store · 14 benchmark_return · 15 portfolio_state · 16 order_event · 17 fill_event", "CodeK")]

priority = [
 ["단계","우선 확보 데이터","주요 대상"],
 ["1. 공통 기반","종목·거래소·자산유형·통화·timezone·주기·OHLCV·adjusted close","Backtrader, Backtesting.py, PyAlgoTrade, QSTrader, PyPortfolioOpt, 기본 FinRL/Freqtrade/Lumibot"],
 ["2. 신뢰도","배당·분할·상장폐지·거래 캘린더·수수료·스프레드·슬리피지·벤치마크","Zipline과 LEAN 포함 주식 백테스트"],
 ["3. 파생·실거래","Bid/Ask, tick, OI, option chain, Greeks, 선물 만기·롤, funding, margin, 주문·체결·계좌","LEAN, Freqtrade 선물, vn.py, pysystemtrade, Lumibot"],
 ["4. AI/RL","기술지표, 거시경제, VIX/turbulence, 뉴스·공시, 상태·행동·보상, 데이터 분할·버전","FinRL, FreqAI, Lumibot AI 전략"],
]
story += [P("8. 구축 우선순위", "H1K"), table(priority,[30*mm,135*mm,83*mm])]

story += [P("9. 최종 권장안", "H1K"),
 P("데이터 계층을 (1) Core Market Data, (2) Asset-Specific Data, (3) Research Data로 분리한다. 공통 market_bar를 중심으로 프로젝트별 어댑터를 만들고, pysystemtrade·LEAN·vn.py처럼 특수 요구가 큰 시스템에는 파생상품 및 실거래 테이블을 추가한다."),
 P("열 이름의 통일보다 더 중요한 것은 원시·조정가격 구분, bar 시작·종료시점, 실제 정보 이용 가능 시각, 종목·거래소·계약월, 시간대, 기업행동 반영방식, 거래 가능 여부, 비용과 거래규칙을 보존하는 것이다."),
 P("주의: bar 데이터만으로는 bar 내부 가격 경로, 정확한 호가순서, 큐 우선순위, 부분체결을 재현할 수 없다. 신호는 완성된 t시점 bar에서 생성하고 체결은 원칙적으로 t+1 이후의 이용 가능한 가격으로 평가해야 미래정보 편향을 줄일 수 있다.")]

story += [PageBreak(), P("참고한 공식 문서", "H1K")]
refs = [
 "Backtrader Data Feed - https://www.backtrader.com/docu/datafeed/",
 "Zipline Reloaded Bundles - https://zipline.ml4trading.io/bundles.html",
 "QuantConnect LEAN Core Data Types - https://www.quantconnect.com/docs/v2/lean-engine/data-format/core-data-types",
 "QuantConnect LEAN Key Concepts - https://www.quantconnect.com/docs/v2/lean-engine/data-format/key-concepts",
 "Freqtrade Strategy DataFrame - https://github.com/freqtrade/freqtrade/blob/develop/docs/strategy-customization.md",
 "FinRL Repository - https://github.com/AI4Finance-Foundation/FinRL",
 "vn.py BarData - https://www.vnpy.com/docs/cn/community/app/script_trader.html",
 "PyPortfolioOpt User Guide - https://pyportfolioopt.readthedocs.io/en/latest/UserGuide.html",
 "pysystemtrade Data - https://github.com/pst-group/pysystemtrade/blob/develop/docs/data.md",
 "pysystemtrade Backtesting - https://github.com/pst-group/pysystemtrade/blob/develop/docs/backtesting.md",
 "Lumibot Data Sources - https://lumibot.lumiwealth.com/lumibot.data_sources.html",
]
for r in refs: story.append(P("• " + r, "SmallK"))

doc = SimpleDocTemplate(str(OUT), pagesize=PAGE, leftMargin=14*mm, rightMargin=14*mm, topMargin=14*mm, bottomMargin=17*mm,
                        title="오픈소스 퀀트 프로젝트 공통·전용 데이터 형식", author="OpenAI Codex")
doc.build(story, onFirstPage=header_footer, onLaterPages=header_footer)

reader = PdfReader(str(OUT))
assert len(reader.pages) >= 6
assert "오픈소스" in "".join((p.extract_text() or "") for p in reader.pages[:2])
print(OUT)
print(f"pages={len(reader.pages)} size={OUT.stat().st_size}")

render_dir = ROOT / "tmp" / "pdfs" / "rendered_opensource_formats"
render_dir.mkdir(parents=True, exist_ok=True)
for old_png in render_dir.glob("page-*.png"):
    old_png.unlink()
pdftoppm = Path(r"C:\Users\user\.cache\codex-runtimes\codex-primary-runtime\dependencies\native\poppler\Library\bin\pdftoppm.exe")
subprocess.run([str(pdftoppm), "-png", "-r", "120", str(OUT), str(render_dir / "page")], check=True)
print(f"rendered={len(list(render_dir.glob('page-*.png')))}")
