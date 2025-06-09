import re
import xml.etree.ElementTree as ET
from xml.dom import minidom
from collections import defaultdict, deque
import subprocess
import cv2
import numpy as np
import os


class FlowDiagramGenerator:
    def __init__(self, input_txt="data/output.txt", output_xml="data/output.drawio"):
        self.input_txt = input_txt
        self.output_xml = output_xml
        self.cell_width = 250
        self.cell_height = 120

    def parse_flow_file(self):
        nodes, edges, children = {}, [], defaultdict(list)
        with open(self.input_txt, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                parts = [p.strip() for p in line.split(';') if p.strip()]
                node_id, desc = parts[0], parts[1]
                nodes[node_id] = desc
                for tgt_part in parts[2:]:
                    m = re.match(r"(?:\[(.*?)\] *-> *)?(\w+)", tgt_part)
                    if m:
                        branch, tgt = m.groups()
                        edges.append({'src': node_id, 'tgt': tgt, 'branch': branch})
                        children[node_id].append(tgt)
        return nodes, edges, children

    def assign_clustered_grid_positions(self, nodes, edges):
        level_map = {}
        parents = defaultdict(set)
        for e in edges:
            parents[e['tgt']].add(e['src'])

        queue = deque([n for n in nodes if n not in parents])
        visited = set()
        while queue:
            node = queue.popleft()
            visited.add(node)
            node_level = max([level_map.get(p, -1) for p in parents[node]], default=-1) + 1
            level_map[node] = node_level
            for e in edges:
                if e['src'] == node and e['tgt'] not in visited:
                    queue.append(e['tgt'])

        level_rows = defaultdict(list)
        for node, lvl in level_map.items():
            level_rows[lvl].append(node)

        positions = {}
        for lvl, row_nodes in sorted(level_rows.items()):
            for i, node in enumerate(sorted(row_nodes)):
                x = i * self.cell_width + 60
                y = lvl * self.cell_height + 40
                positions[node] = (x, y)

        for node in nodes:
            if node not in positions:
                positions[node] = (60, (len(positions) + 1) * self.cell_height + 40)

        return positions

    def build_drawio_xml(self, nodes, edges, positions):
        mxfile = ET.Element("mxfile", host="app.diagrams.net")
        diagram = ET.SubElement(mxfile, "diagram", name="Flow")
        model = ET.SubElement(diagram, "mxGraphModel")
        root = ET.SubElement(model, "root")
        ET.SubElement(root, "mxCell", id="0")
        ET.SubElement(root, "mxCell", id="1", parent="0")

        for nid, desc in nodes.items():
            x, y = positions[nid]
            style = "rhombus" if nid.startswith("D") else "rounded=1"
            cell = ET.SubElement(
                root,
                "mxCell",
                id=nid,
                value=desc,
                style=f"{style};whiteSpace=wrap;html=1;",
                vertex="1",
                parent="1",
            )
            ET.SubElement(cell, "mxGeometry", x=str(x), y=str(y), width="170", height="60", as_="geometry")

        for idx, edge in enumerate(edges):
            eid = f"e{idx + 1}"
            attrs = {
                "id": eid,
                "edge": "1",
                "source": edge['src'],
                "target": edge['tgt'],
                "parent": "1",
                "style": "orthogonalEdgeStyle;endArrow=block;html=1;",
            }
            ecell = ET.SubElement(root, "mxCell", **attrs)
            ET.SubElement(ecell, "mxGeometry", relative="1", as_="geometry")
            if edge['branch']:
                label_cell = ET.SubElement(
                    root,
                    "mxCell",
                    value=edge['branch'],
                    style="edgeLabel;html=1;",
                    vertex="1",
                    connectable="0",
                    parent=eid,
                )
                ET.SubElement(label_cell, "mxGeometry", x="0.5", y="-0.7", relative="1", as_="geometry")

        return (
            minidom.parseString(ET.tostring(mxfile))
            .toprettyxml(indent="  ")
            .replace('as_="geometry"', 'as="geometry"')
        )

    def render_and_validate(self):
        output_dir = "data/image"
        os.makedirs(output_dir, exist_ok=True)
        output_png = os.path.join(output_dir, "diagram.png")
        drawio_path = r"C:\Program Files\draw.io\drawio.exe"
        try:
            cache_dir = os.path.expanduser(r"~\drawio\cache")
            os.makedirs(cache_dir, exist_ok=True)
            subprocess.run(
                [
                    drawio_path,
                    f"--user-data-dir={cache_dir}",
                    "-x",
                    "-f",
                    "png",
                    "-o",
                    output_png,
                    self.output_xml,
                ],
                check=True,
            )
        except subprocess.CalledProcessError as e:
            print(f"Draw.io CLI error: {e}")
            return False
        except FileNotFoundError:
            print(f"Draw.io CLI not found at '{drawio_path}'")
            return False

        img = cv2.imread(output_png, 0)
        edges = cv2.Canny(img, 50, 150)
        lines = cv2.HoughLinesP(edges, 1, np.pi / 180, threshold=100, minLineLength=50, maxLineGap=5)
        return lines is None or len(lines) < 5

    def refine_until_clean(self, max_attempts=5):
        for attempt in range(max_attempts):
            nodes, edges, _ = self.parse_flow_file()
            positions = self.assign_clustered_grid_positions(nodes, edges)
            xml_out = self.build_drawio_xml(nodes, edges, positions)
            with open(self.output_xml, "w", encoding="utf-8") as f:
                f.write(xml_out)
            if self.render_and_validate():
                print("\u2705 Clean diagram generated.")
                return
            else:
                self.cell_width += 40
                self.cell_height += 30
                print(f"Retrying with more spacing... (attempt {attempt + 1})")


if __name__ == "__main__":
    FlowDiagramGenerator().refine_until_clean()
