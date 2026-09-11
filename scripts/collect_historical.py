#!/usr/bin/env python3
"""
1년 역사 데이터 수집 스크립트 (진행도 표시 포함)
기간: 2025-09-01 ~ 2026-08-31

피드별 전략:
  bids     : 12개 월간 윈도우 (× 1 코드)    = 12  논리 윈도우
  awards   : 365개 일간 윈도우 (× 4 업무구분) = 1,460 논리 윈도우
  contracts: 53개 주간 윈도우 (× 1 코드)    = 53  논리 윈도우
  합계                                      = 1,525 논리 윈도우

사용법 (Git Bash):
  python scripts/collect_historical.py
  python scripts/collect_historical.py --dataset bids     # 특정 피드만
  python scripts/collect_historical.py --dataset awards
  python scripts/collect_historical.py --dataset contracts
  python scripts/collect_historical.py --resume           # 이미 완료 윈도우 건너뜀 (기본)
  python scripts/collect_historical.py --force            # 전체 재수집

쿼터 소진 시:
  수집이 안전하게 중단되고 매니페스트에 진행 상태가 보존됩니다.
  다음 날 동일 명령어로 재실행하면 완료된 윈도우를 건너뛰고 이어집니다.
"""
from __future__ import annotations

import argparse
import sys
import time
from datetime import date, datetime, timezone
from pathlib import Path

try:
    from tqdm import tqdm
    HAS_TQDM = True
except ImportError:
    HAS_TQDM = False

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from koneps_intel.api import AuthenticationError, KonepsClient, QuotaExceededError
from koneps_intel.collector import Collector, CollectionStats
from koneps_intel.config import RAW_DIR, get_service_key, mask_key
from koneps_intel.endpoints import BUSINESS_DIVISIONS, DEFAULT_PAGE_SIZE, FEEDS
from koneps_intel.parsers import feed_windows, parse_date
from koneps_intel.storage import ManifestManager
from koneps_intel.utils import get_logger

HISTORICAL_START = "2025-09-01"
HISTORICAL_END   = "2026-08-31"


def count_total_windows(dataset: str, start: date, end: date) -> int:
    """미리 전체 논리 윈도우 수를 계산."""
    selected = list(FEEDS) if dataset == "all" else [dataset]
    total = 0
    for name in selected:
        spec = FEEDS[name]
        codes = list(BUSINESS_DIVISIONS.keys()) if spec.needs_business_division else [None]
        wins = list(feed_windows(spec, start, end))
        total += len(wins) * len(codes)
    return total


def collect_with_progress(
    collector: Collector,
    dataset: str,
    start: date,
    end: date,
    page_size: int,
    force: bool,
    logger,
) -> CollectionStats:
    """진행도 바 표시와 함께 수집 루프 실행."""
    selected = list(FEEDS) if dataset == "all" else [dataset]
    stats = CollectionStats()
    session_start = time.time()

    # 전체 윈도우 수 계산 (진행바 total)
    total_windows = count_total_windows(dataset, start, end)
    windows_processed = 0
    windows_skipped = 0

    logger.info(
        "START 1-year historical collection | feeds=%s | %s~%s | total_logical_windows=%d",
        selected, start, end, total_windows,
    )

    if HAS_TQDM:
        pbar = tqdm(
            total=total_windows,
            unit="win",
            desc="전체",
            bar_format=(
                "{desc}: {percentage:5.1f}%|{bar:40}| "
                "{n_fmt}/{total_fmt} win "
                "[경과:{elapsed} 남은:{remaining} {rate_fmt}]"
            ),
            dynamic_ncols=True,
        )
    else:
        pbar = None

    try:
        for name in selected:
            spec = FEEDS[name]
            codes = list(BUSINESS_DIVISIONS.keys()) if spec.needs_business_division else [None]
            calendar_windows = list(feed_windows(spec, start, end))

            if pbar:
                pbar.set_description(f"{name:9s}")

            for win_idx, (win_start, win_end) in enumerate(calendar_windows):
                for code_idx, code in enumerate(codes):
                    code_label = code or "all"
                    try:
                        rows, calls, _ = collector.collect_window(
                            spec=spec,
                            start=win_start,
                            end=win_end,
                            page_size=page_size,
                            business_code=code,
                            force=force,
                            dry_run=False,
                        )
                        stats.total_rows += rows
                        stats.total_calls += calls
                        windows_processed += 1

                        if rows == 0 and calls == 0:
                            stats.skipped_windows += 1
                            windows_skipped += 1
                            status_str = "SKIP"
                        else:
                            stats.completed_windows += 1
                            status_str = f"+{rows:,}행"

                    except QuotaExceededError:
                        if pbar:
                            pbar.close()
                        elapsed = time.time() - session_start
                        logger.error(
                            "쿼터 소진 — 안전하게 중단. 완료=%d/%d 윈도우 | 수집행=%s | API호출=%d | 경과=%.0fs",
                            windows_processed, total_windows,
                            f"{stats.total_rows:,}", stats.total_calls, elapsed,
                        )
                        logger.error("내일 동일 명령어로 재실행하면 완료된 윈도우를 건너뛰고 자동 재개됩니다.")
                        raise

                    if pbar:
                        elapsed = time.time() - session_start
                        rate = stats.total_rows / elapsed if elapsed > 0 else 0
                        pbar.set_postfix(
                            rows=f"{stats.total_rows:,}",
                            calls=stats.total_calls,
                            skip=windows_skipped,
                            last=f"{win_start}/{code_label}:{status_str}",
                            refresh=False,
                        )
                        pbar.update(1)
                    else:
                        # tqdm 없을 때 주기적 로그
                        if windows_processed % 50 == 0 or windows_processed == 1:
                            pct = 100 * windows_processed / total_windows
                            logger.info(
                                "진행: %d/%d (%.1f%%) | %s | rows=%s | calls=%d | skip=%d",
                                windows_processed, total_windows, pct,
                                f"{win_start}~{win_end}/{code_label}",
                                f"{stats.total_rows:,}", stats.total_calls, windows_skipped,
                            )

    finally:
        if pbar:
            pbar.close()

    elapsed = time.time() - session_start
    logger.info(
        "DONE | windows=%d/%d | skipped=%d | total_rows=%s | api_calls=%d | elapsed=%.0fs (%.1fmin)",
        windows_processed, total_windows, windows_skipped,
        f"{stats.total_rows:,}", stats.total_calls,
        elapsed, elapsed / 60,
    )
    return stats


def main() -> None:
    parser = argparse.ArgumentParser(
        description="KONEPS 1년 역사 데이터 수집 (2025-09-01 ~ 2026-08-31)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--dataset",
        choices=["all", "bids", "awards", "contracts"],
        default="all",
        help="수집할 피드 (기본: all — bids → awards → contracts 순서)",
    )
    parser.add_argument(
        "--start",
        default=HISTORICAL_START,
        help=f"시작일 (기본: {HISTORICAL_START})",
    )
    parser.add_argument(
        "--end",
        default=HISTORICAL_END,
        help=f"종료일 (기본: {HISTORICAL_END})",
    )
    parser.add_argument(
        "--out",
        default=str(RAW_DIR),
        help="원천 데이터 저장 디렉터리 (기본: data/raw)",
    )
    parser.add_argument(
        "--page-size",
        type=int,
        default=DEFAULT_PAGE_SIZE,
        help=f"페이지 크기 (기본: {DEFAULT_PAGE_SIZE})",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="이미 완료된 윈도우도 강제 재수집 (기본: 건너뜀)",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        default=True,
        help="완료된 윈도우 건너뜀 (기본 동작 — 플래그 불필요)",
    )
    parser.add_argument(
        "--pause",
        type=float,
        default=0.08,
        help="API 호출 사이 대기 시간 초 (기본: 0.08s)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="실제 API 호출 없이 계획만 출력",
    )
    args = parser.parse_args()

    logger = get_logger("koneps_historical")

    if not 1 <= args.page_size <= 999:
        parser.error("--page-size는 1~999 사이여야 합니다")

    try:
        start = parse_date(args.start)
        end = parse_date(args.end)
    except ValueError as e:
        parser.error(f"날짜 형식 오류: {e}")

    if start > end:
        parser.error("--start는 --end 이하여야 합니다")

    # 드라이런: 플래너 출력만
    if args.dry_run:
        total = count_total_windows(args.dataset, start, end)
        selected = list(FEEDS) if args.dataset == "all" else [args.dataset]
        print(f"\n{'='*60}")
        print(f"드라이런 - KONEPS 역사 수집 계획")
        print(f"{'='*60}")
        print(f"피드    : {selected}")
        print(f"기간    : {start} ~ {end}")
        print(f"API 호출: 0회 (드라이런)")
        print()
        for name in selected:
            spec = FEEDS[name]
            codes = list(BUSINESS_DIVISIONS.keys()) if spec.needs_business_division else [None]
            wins = list(feed_windows(spec, start, end))
            lw = len(wins) * len(codes)
            print(f"  {name:12s}: {len(wins):3d} 캘린더 윈도우 × {len(codes)} 코드 = {lw:5d} 논리 윈도우")
        print(f"  {'합계':12s}: {total:5d} 논리 윈도우")
        print(f"{'='*60}\n")
        return

    try:
        service_key = get_service_key(required=True)
    except RuntimeError as err:
        logger.error("%s", err)
        sys.exit(1)

    logger.info("서비스키: %s", mask_key(service_key))

    client = KonepsClient(service_key=service_key, pause=args.pause, logger=logger)
    collector = Collector(client=client, out_dir=Path(args.out), logger=logger)

    try:
        stats = collect_with_progress(
            collector=collector,
            dataset=args.dataset,
            start=start,
            end=end,
            page_size=args.page_size,
            force=args.force,
            logger=logger,
        )
        print(f"\n{'='*60}")
        print("수집 완료 요약")
        print(f"{'='*60}")
        print(f"  완료 윈도우 : {stats.completed_windows:,}")
        print(f"  건너뛴 윈도우: {stats.skipped_windows:,} (이미 수집됨)")
        print(f"  총 수집 행수 : {stats.total_rows:,}")
        print(f"  총 API 호출  : {stats.total_calls:,}")
        print(f"{'='*60}")
        print(
            "  NEXT: python scripts/build_dataset.py --start 2025-09-01 --end 2026-08-31 "
            "--processed data/processed/historical_202509_202608"
        )
        print(f"{'='*60}\n")

    except AuthenticationError as e:
        logger.error("인증 실패: %s", e)
        sys.exit(2)
    except QuotaExceededError:
        logger.error("일일 쿼터 소진. 내일 동일 명령어로 재개하세요.")
        sys.exit(3)
    except Exception as e:
        logger.exception("예상치 못한 오류: %s", e)
        sys.exit(1)


if __name__ == "__main__":
    main()
