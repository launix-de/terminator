"""Compatibility helpers to bridge GTK3→GTK4 API differences.

These are intended to be used during the transition; once the codebase
is fully GTK4, most of these can be inlined and simplified.
"""

def container_add(container, child):
    # Gtk4 containers typically expose append()/prepend() or set_child()
    if hasattr(container, 'append'):
        return container.append(child)
    if hasattr(container, 'set_child'):
        return container.set_child(child)
    # Gtk3 fallback
    return container.add(child)


def scrolled_set_child(scroller, child):
    if hasattr(scroller, 'set_child'):
        return scroller.set_child(child)
    return scroller.add(child)


def box_append(box, child):
    if hasattr(box, 'append'):
        return box.append(child)
    # Gtk3 fallback: pack_end to mimic default append at end
    if hasattr(box, 'pack_end'):
        return box.pack_end(child, True, True, 0)
    return box.add(child)

