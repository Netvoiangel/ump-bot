import pytest
from datetime import date
from pathlib import Path
from src.ump_bot.domain.warranty_act import WarrantyActData
from src.ump_bot.services.warranty_act import generate_warranty_act, ACT_TEMPLATE_PATH

@pytest.mark.skipif(not ACT_TEMPLATE_PATH.exists(), reason="Template file not found")
def test_generate_warranty_act(tmp_path):
    data = WarrantyActData(
        act_date=date(2026, 1, 31),
        park_name="Энергетиков",
        address="пр. Энергетиков, д. 50",
        request_no="12345",
        license_plate="А123АА77",
        garage_no="6563",
        reported_fault="Не включается",
        diagnostic_result="Сгорел БП",
        performed_works="Замена БП",
        executor_name="Иванов Иван Иванович",
        start_date=date(2026, 1, 31),
        end_date=date(2026, 1, 31),
        validator_type="BM-20",
        old_validator_sn="SN123",
        new_validator_sn="SN456",
        old_sam_sn="SAM123",
        new_sam_sn="SAM456",
        old_sam_activation_no="ACT123",
        new_sam_activation_no="ACT456"
    )
    
    # We can't easily test docx content without more dependencies, 
    # but we can check if the file is created.
    # Note: generate_warranty_act saves to CACHE_DIR/acts, not tmp_path here.
    # For testing, we might want to mock CACHE_DIR or let it write there.
    
    path_str = generate_warranty_act(data)
    path = Path(path_str)
    
    assert path.exists()
    assert path.suffix == ".docx"
    assert "12345" in path.name
    assert "6563" in path.name
    
    # Clean up
    if path.exists():
        path.unlink()
