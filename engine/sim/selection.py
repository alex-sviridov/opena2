"""Selection system: applies `SelectUnits` commands to `Player.selection`."""

from .commands import SelectUnits


def _dedupe(ids):
    return tuple(dict.fromkeys(ids))


def selection_system(world, commands):
    """Apply every SelectUnits in order; rejected commands leave the selection unchanged."""
    for cmd in commands:
        if not isinstance(cmd, SelectUnits):
            continue
        player = world.players.get(cmd.player_id)
        if player is None:
            continue
        ids = _dedupe(i for i in cmd.unit_ids if i in world.units)
        owned = [world.units[i].owner == cmd.player_id for i in ids]
        if cmd.toggle:
            if world.selection_is_foreign(cmd.player_id):
                continue
            sel = list(player.selection)
            for i, own in zip(ids, owned):
                if own:
                    sel.remove(i) if i in sel else sel.append(i)
            player.selection = tuple(sel)
        elif not ids or all(owned) or len(ids) == 1:
            player.selection = ids
