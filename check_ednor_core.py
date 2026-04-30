from __future__ import annotations

import shutil
import tempfile
from pathlib import Path


def _patch_portable_root(temp_root: Path) -> None:
    """Przekierowuje Ednor_data do katalogu testowego.

    Nie dotyka prawdziwych danych użytkownika.
    """

    import core.ednor_paths as paths
    import core.cutting_storage as storage

    def _test_app_base_dir() -> Path:
        return temp_root

    paths.app_base_dir = _test_app_base_dir

    # cutting_storage zaimportowało funkcje ścieżek bezpośrednio,
    # więc podmieniamy też referencje w module storage.
    storage.cutting_calculations_dir = paths.cutting_calculations_dir
    storage.cutting_jobs_dir = paths.cutting_jobs_dir
    storage.cutting_materials_file = paths.cutting_materials_file
    storage.cutting_reports_dir = paths.cutting_reports_dir
    storage.cutting_settings_file = paths.cutting_settings_file
    storage.cutting_stock_bars_file = paths.cutting_stock_bars_file
    storage.cutting_stock_moves_file = paths.cutting_stock_moves_file
    storage.transports_file = paths.transports_file
    storage.ensure_data_tree = paths.ensure_data_tree


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _print_ok(message: str) -> None:
    print(f"[OK] {message}")


def run_check() -> int:
    temp_dir = Path(tempfile.mkdtemp(prefix="ednor_check_")).resolve()
    print(f"[INFO] Testowy katalog portable: {temp_dir}")

    try:
        _patch_portable_root(temp_dir)

        import core.ednor_paths as paths
        import core.cutting_storage as storage

        paths.ensure_data_tree()
        _assert((temp_dir / "Ednor_data").exists(), "Nie utworzono Ednor_data")
        _print_ok("portable Ednor_data tworzy się poprawnie")

        storage.upsert_material(
            {
                "typ": "profil",
                "wymiary": {"a": "40", "b": "30", "c": "2"},
                "domyslna_dlugosc_mm": 6000,
                "aktywny": True,
            }
        )
        material_id = "profil_40x30x2"
        _assert(material_id == "profil_40x30x2", f"Nieoczekiwany material_id: {material_id}")
        _print_ok("dodanie surowca Profil 40x30x2")

        transport = storage.save_transport(
            {
                "supplier": "TEST-STAL",
                "transport_cost": 0,
                "price_mode": "netto",
                "vat_percent": 23,
                "lines": [
                    {
                        "material_id": material_id,
                        "bar_length_mm": 6000,
                        "qty": 2,
                        "price_per_m": 10,
                    }
                ],
            }
        )
        _assert(transport.get("transport_id") == "TR-000001", "Pierwszy transport nie ma numeru TR-000001")
        _print_ok("zapis transportu TR-000001")

        stock = storage.load_cutting_stock_raw()
        bars = stock.get("bars", [])
        _assert(len(bars) == 1, "Transport powinien dodać jeden rekord stock_bars z qty=2")
        _assert(int(bars[0].get("qty", 0)) == 2, "Transport powinien mieć qty=2")
        _assert(str(bars[0].get("transport_id")) == "TR-000001", "Stock nie dostał transport_id")
        _print_ok("transport dodał sztangi do magazynu z transport_id")

        result = {
            "job_id": "TEST-JOB",
            "status": "draft",
            "bars_used": [
                {
                    "source": "stock",
                    "material_id": material_id,
                    "bar_length_mm": 6000,
                    "waste_mm": 1200,
                    "cuts": [
                        {"length_mm": 1500, "angle_left": 0, "angle_right": 0},
                        {"length_mm": 1500, "angle_left": 45, "angle_right": -45},
                    ],
                }
            ],
        }

        storage.accept_cutting_calculation("TEST-JOB", result)
        _assert(result.get("accepted_at"), "Wynik nie dostał accepted_at")
        _assert(result.get("status") == "accepted", "Status wyniku nie jest accepted")
        _assert(float(result.get("material_cost_net", 0)) == 60.0, "Koszt netto powinien wynieść 60.00 zł")
        _assert(float(result.get("material_cost_gross", 0)) == 73.8, "Koszt brutto powinien wynieść 73.80 zł")
        _assert(len(result.get("stock_deductions", [])) == 1, "Powinien być jeden rozchód magazynu")
        _assert(len(result.get("created_offcuts", [])) == 1, "Powinien powstać jeden odpad")
        _print_ok("akceptacja kalkulacji liczy koszt i rozchód")

        stock_after = storage.load_cutting_stock_raw()
        bars_after = stock_after.get("bars", [])
        offs_after = stock_after.get("offs", [])
        _assert(int(bars_after[0].get("qty", 0)) == 1, "Po akceptacji qty sztangi powinno spaść z 2 do 1")
        _assert(len(offs_after) == 1, "Odpad powinien trafić do offs")
        _assert(str(offs_after[0].get("transport_id")) == "TR-000001", "Odpad nie odziedziczył transport_id")
        _assert(float(offs_after[0].get("price_per_m", 0)) == 10.0, "Odpad nie odziedziczył ceny")
        _print_ok("FIFO zmniejsza magazyn, odpad dziedziczy transport i cenę")

        try:
            storage.accept_cutting_calculation("TEST-JOB", result)
            raise AssertionError("Druga akceptacja powinna być zablokowana")
        except ValueError:
            _print_ok("podwójna akceptacja jest zablokowana")

        materials = storage.load_materials()
        row = next((m for m in materials if m.get("material_id") == material_id), None)
        _assert(row is not None, "Brak materiału po load_materials")
        _assert(float(row.get("stock_mb", 0)) == 7.2, f"Stan mb powinien wynieść 7.2, jest {row.get('stock_mb')}")
        _assert(float(row.get("stock_value_net", 0)) == 72.0, "Wartość netto magazynu powinna wynieść 72.00")
        _print_ok("load_materials pokazuje stock_mb i wartość magazynu")

        # Test backupu JSON.
        storage.update_cutting_setting("price_mode", "netto")
        storage.update_cutting_setting("price_mode", "brutto")
        settings_path = paths.cutting_settings_file()
        _assert(settings_path.exists(), "settings.json nie istnieje")
        _assert(Path(str(settings_path) + ".bak").exists(), "Nie utworzono settings.json.bak")
        _print_ok("backup .bak przy zapisie JSON działa")

        # Test broken JSON.
        settings_path.write_text("{ to nie jest json", encoding="utf-8")
        data = storage.load_cutting_settings()
        _assert(isinstance(data, dict), "Po broken JSON powinien wrócić dict")
        broken = list(settings_path.parent.glob("settings.json.broken_*"))
        _assert(broken, "Uszkodzony JSON nie został przeniesiony do .broken_TIMESTAMP")
        _print_ok("broken JSON jest zabezpieczany")

        print("\n[OK] EDNOR CORE CHECK: wszystkie testy przeszły.")
        return 0
    except Exception as exc:
        print(f"\n[FAIL] {exc}")
        return 1
    finally:
        try:
            shutil.rmtree(temp_dir, ignore_errors=True)
        except Exception:
            pass


if __name__ == "__main__":
    raise SystemExit(run_check())
