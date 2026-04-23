import os
import sys
import logging

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.database import DatabaseManager
from src.evaluator import QualityEvaluator

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def main():
    db = DatabaseManager()
    evaluator = QualityEvaluator(db)
    
    logger.info("Bắt đầu đánh giá chất lượng...")
    eval_results = evaluator.evaluate_batch()
    
    print("\n" + "="*50)
    print(" BÁO CÁO ĐÁNH GIÁ CHẤT LƯỢNG (EVALUATION REPORT)")
    print("="*50)
    print(f"Overall Quality Score (0-100): {eval_results['overall_quality_score']}")
    
    print("\n--- Phân bổ chất lượng (Grade Distribution) ---")
    for grade, count in eval_results['grade_distribution'].items():
        print(f"{grade.ljust(15)}: {count}")
    
    print("\n--- Vấn đề phổ biến (Common Issues) ---")
    for idx, issue in enumerate(eval_results['common_issues'], 1):
        print(f"{idx}. {issue}")
        
    print("\n--- Đề xuất (Recommendations) ---")
    for idx, rec in enumerate(eval_results['recommendations'], 1):
        print(f"{idx}. {rec}")
        
    output_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "output")
    os.makedirs(output_dir, exist_ok=True)
    report_path = os.path.join(output_dir, "evaluation_report.xlsx")
    
    evaluator.generate_evaluation_report(report_path, eval_results)
    logger.info(f"Đã xuất báo cáo chi tiết ra file: {report_path}")

if __name__ == "__main__":
    main()
