"""
导入 Golden Cases 到评测平台

用法:
    python -m app.scripts.import_golden_cases [--dataset-name NAME] [--version VERSION]
"""

import asyncio
import json
import logging
import sys
from pathlib import Path

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.core.database import db_manager
from app.services.eval.dataset_service import dataset_service

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def import_golden_cases(
    dataset_name: str = "Vibe Agent Golden Set V1",
    version: str = "1.0.0",
):
    """导入 golden cases"""

    # 初始化数据库
    await db_manager.init_mongodb()

    # 初始化服务
    await dataset_service.initialize()

    # 加载 golden cases 数据
    data_file = Path(__file__).parent.parent / "services" / "eval" / "data" / "golden_cases.json"
    if not data_file.exists():
        logger.error(f"Golden cases file not found: {data_file}")
        return

    with open(data_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    dataset_config = data["dataset"]
    cases = data["cases"]

    logger.info(f"Loaded {len(cases)} cases from {data_file}")

    # 创建数据集
    try:
        result = await dataset_service.create_dataset(
            name=dataset_name,
            description=dataset_config.get("description", ""),
            tags=dataset_config.get("tags", []),
            created_by="system",
        )
        dataset_id = result["dataset_id"]
        logger.info(f"Created dataset: {dataset_id}")
    except Exception as e:
        logger.warning(f"Dataset may already exist: {e}")
        # 尝试获取现有数据集
        datasets = await dataset_service.list_datasets(limit=1)
        if datasets:
            dataset_id = datasets[0]["dataset_id"]
            logger.info(f"Using existing dataset: {dataset_id}")
        else:
            logger.error("Failed to create or find dataset")
            return

    # 更新版本
    await dataset_service.update_dataset(dataset_id, status="active")

    # 导入用例
    imported_count = 0
    for case_data in cases:
        try:
            await dataset_service.add_case(
                dataset_id=dataset_id,
                name=case_data["name"],
                input_data=case_data["input"],
                expected_output=case_data.get("expected_output"),
                scoring_criteria=case_data.get("scoring_criteria", {}),
                tags=case_data.get("tags", []),
                difficulty=case_data.get("difficulty", "medium"),
                category=case_data.get("category", "general"),
                description=case_data.get("description", ""),
            )
            imported_count += 1
            logger.info(f"Imported case: {case_data['case_id']} - {case_data['name']}")
        except Exception as e:
            logger.error(f"Failed to import case {case_data['case_id']}: {e}")

    logger.info(f"Import completed: {imported_count}/{len(cases)} cases")

    # 关闭数据库连接
    await db_manager.close_all()


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Import golden cases for evaluation platform")
    parser.add_argument("--dataset-name", default="Vibe Agent Golden Set V1", help="Dataset name")
    parser.add_argument("--version", default="1.0.0", help="Dataset version")

    args = parser.parse_args()

    asyncio.run(import_golden_cases(args.dataset_name, args.version))


if __name__ == "__main__":
    main()
