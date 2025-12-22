from src.ump_bot.infra.render_map import _tile_canvas_is_too_big, _tile_grid_metrics


def test_tile_grid_metrics_reasonable_for_small_bbox():
    # небольшой bbox вокруг парка (пример из parks.json)
    bbox = (30.440692, 59.961891, 30.444692, 59.964766)
    tiles_x, tiles_y, w, h = _tile_grid_metrics(bbox, zoom=17)
    assert tiles_x > 0 and tiles_y > 0
    assert w == tiles_x * 256
    assert h == tiles_y * 256


def test_tile_canvas_guard_triggers_for_world_sized_bbox():
    # bbox почти на весь мир -> на высоком zoom даст очень много тайлов
    bbox = (-179.0, -80.0, 179.0, 80.0)
    assert _tile_canvas_is_too_big(bbox, zoom=17, max_tiles=225)


