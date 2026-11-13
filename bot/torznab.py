"""Small, dependency-free parser for Jackett Torznab RSS responses."""

import xml.etree.ElementTree as ET


def _local_name(tag):
    """Return an XML tag's local name, regardless of its namespace."""
    return tag.rsplit("}", 1)[-1].lower()


def _child_text(element, name):
    for child in element:
        if _local_name(child.tag) == name:
            return (child.text or "").strip()
    return ""


def parse_torznab_results(xml_content, limit=10):
    """Parse Torznab items into the fields consumed by the Telegram bot.

    Torznab commonly returns the torrent size as an RSS <size> child element,
    while seeders and magnet URLs are usually torznab:attr elements. Some
    indexers also expose size as an attr, so that is supported as a fallback.
    """
    root = ET.fromstring(xml_content)

    for element in root.iter():
        if _local_name(element.tag) == "error":
            code = element.attrib.get("code", "")
            description = element.attrib.get("description", "Unknown Torznab error")
            detail = f" (code {code})" if code else ""
            raise RuntimeError(f"Jackett/Torznab API error{detail}: {description}")

    results = []
    for item in root.iter():
        if _local_name(item.tag) != "item":
            continue

        title = _child_text(item, "title") or "未命名资源"
        link = _child_text(item, "link")
        seeders = _child_text(item, "seeders")
        size = _child_text(item, "size")
        magnet = ""

        for element in item.iter():
            if _local_name(element.tag) != "attr":
                continue
            name = element.attrib.get("name", "").lower()
            value = element.attrib.get("value", "").strip()
            if name == "seeders" and not seeders:
                seeders = value
            elif name == "size" and not size:
                size = value
            elif name == "magneturl" and not magnet:
                magnet = value

        if not magnet and link.startswith("magnet:"):
            magnet = link

        download_url = magnet or link
        if download_url.startswith(("magnet:", "http://", "https://")):
            results.append({
                "title": title,
                "url": download_url,
                "seeders": seeders,
                "size": size,
            })

    results.sort(
        key=lambda row: int(row["seeders"]) if row["seeders"].isdigit() else -1,
        reverse=True,
    )
    return results[:max(1, int(limit))]
