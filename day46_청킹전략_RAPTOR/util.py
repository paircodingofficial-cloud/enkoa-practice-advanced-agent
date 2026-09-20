from langchain_core.documents import Document


def nodes_to_documents(nodes, all_nodes=None, records_by_id=None):
    """파서 노드를 Document로 옮기고, 겹침 0인 계층의 위치를 원문과 대조합니다."""
    # 계층 검색 결과에는 일부 노드만 있으므로 전체 계층을 함께 받아 부모를 조회합니다.
    nodes_by_id = {
        node.node_id: node for node in (all_nodes if all_nodes is not None else nodes)
    }
    relative_starts = {}

    if all_nodes is not None:
        if records_by_id is None:
            raise ValueError("계층 위치를 연결하려면 records_by_id에 청킹 전 원문을 전달하세요.")
        next_positions = {}

        for item in all_nodes:
            if item.parent_node is None:
                source_id = item.metadata["source_id"]
                original = records_by_id[source_id]["text"]
                group = ("source", source_id)
            else:
                parent_id = item.parent_node.node_id
                original = nodes_by_id[parent_id].text
                group = ("parent", parent_id)

            # 이 실습의 계층은 겹침 0입니다. 같은 부모의 앞 청크 끝 다음부터 찾습니다.
            cursor = next_positions.get(group, 0)
            start = original.find(item.text, cursor) if item.text.strip() else -1
            if start < 0 or original[cursor:start].strip():
                raise ValueError("계층 노드의 원문 순서·겹침 0 설정과 본문 일치를 확인하세요.")
            relative_starts[item.node_id] = start
            next_positions[group] = start + len(item.text)

    result = []
    for node in nodes:
        if node.parent_node is not None and all_nodes is None:
            raise ValueError("계층 노드를 변환할 때 전체 계층과 청킹 전 원문을 함께 전달하세요.")

        metadata = dict(node.metadata)
        anchor = (
            relative_starts[node.node_id]
            if all_nodes is not None else node.start_char_idx
        )
        parent = node

        # 자식의 위치는 바로 위 부모 본문의 시작을 기준으로 하므로 부모 위치를 차례로 더합니다.
        while parent.parent_node is not None and anchor is not None:
            parent_id = parent.parent_node.node_id
            if parent_id not in nodes_by_id:
                raise ValueError("계층 노드를 변환할 때 all_nodes에 전체 계층을 전달하세요.")
            parent = nodes_by_id[parent_id]
            parent_start = relative_starts[parent_id]
            anchor += parent_start

        metadata.pop("parser_start_index", None)
        if anchor is not None and parent.ref_doc_id == metadata["source_id"]:
            # Window로 본문을 넓혀도 검색한 문장의 첫 글자는 반환 구간 안에 남습니다.
            metadata["parser_start_index"] = (
                anchor + len(node.text) - len(node.text.lstrip())
            )
        result.append(Document(page_content=node.text, metadata=metadata))

    return result


def restore_positions(contexts, records_by_id, sequential=False):
    """원문 구간을 붙입니다. 초기 문장·의미 파서의 전체 결과만 sequential=True로 받습니다."""
    unique = {}
    normalized_sources = {}
    next_positions = {}

    for doc in contexts:
        source_id = doc.metadata["source_id"]
        original = records_by_id[source_id]["text"]
        text = doc.page_content

        # 초기 파서는 START+1에서 중복 문구를 찾아 앞 문장의 어미를 오인할 수 있습니다.
        # 전체 파서 결과를 처음 변환할 때는 그 위치 대신 이전 문장·청크의 END를 사용합니다.
        cursor = next_positions.get(source_id, 0) if sequential else 0
        anchor = None if sequential else doc.metadata.get("parser_start_index")
        # 원래 노드는 첫 글자 위치까지 같아야 합니다. Window만 검색 문장을 내부에 포함합니다.
        expanded_window = text == doc.metadata.get("window")
        leading_spaces = len(text) - len(text.lstrip())

        matches = []
        # 본문이 그대로이면 기준점 주변만 직접 찾습니다.
        search_start = max(0, anchor - len(text)) if anchor is not None else cursor
        search_end = (
            min(len(original), anchor + len(text))
            if anchor is not None else len(original)
        )
        start = original.find(text, search_start, search_end) if text else -1

        while start >= 0:
            end = start + len(text)
            matches_anchor = (
                start <= anchor < end
                if expanded_window and anchor is not None
                else start + leading_spaces == anchor
            )
            if anchor is None or matches_anchor:
                if not sequential or not original[cursor:start].strip():
                    matches.append((start, end))
                if sequential:
                    break
                if len(matches) > 1:
                    break
            start = original.find(text, start + 1, search_end)

        if not matches:
            # Window는 문장 사이 공백을 바꿀 수 있습니다. 이때만 공백을 제외하고 대조합니다.
            # 한 번 호출하는 동안 같은 원문은 한 번만 정리하고 글자별 원래 위치를 보관합니다.
            if source_id not in normalized_sources:
                positions = [
                    index for index, char in enumerate(original) if not char.isspace()
                ]
                normalized_sources[source_id] = (
                    "".join(original[index] for index in positions), positions
                )

            normalized, positions = normalized_sources[source_id]
            target = "".join(char for char in text if not char.isspace())
            match_start = normalized.find(target) if target else -1

            while match_start >= 0:
                start = positions[match_start]
                end = positions[match_start + len(target) - 1] + 1
                matches_anchor = (
                    start <= anchor < end
                    if expanded_window and anchor is not None
                    else start == anchor
                )
                if start >= cursor and (anchor is None or matches_anchor):
                    if not sequential or not original[cursor:start].strip():
                        matches.append((start, end))
                    if sequential:
                        break
                    if len(matches) > 1:
                        break
                match_start = normalized.find(target, match_start + 1)

        # 하나로 정해지지 않으면 엉뚱한 위치로 채점하지 않도록 멈춥니다.
        if len(matches) != 1:
            raise ValueError(f"원문에서 구간을 하나로 찾을 수 없습니다: {source_id}")
        start, end = matches[0]

        # 공백까지 원문과 같도록 본문을 원문 조각으로 바꾸고 위치를 적습니다.
        doc.page_content = original[start:end]
        doc.metadata.update(start_index=start, end_index=end)
        if sequential:
            next_positions[source_id] = end
            # 검색 후 Window를 넓힐 때에도 사용할 수 있도록 바로잡은 기준점을 저장합니다.
            doc.metadata["parser_start_index"] = (
                start + len(doc.page_content) - len(doc.page_content.lstrip())
            )

        # 이웃 문장의 Window가 같은 구간이 되면 한 번만 남깁니다.
        unique[(source_id, start, end)] = doc

    return list(unique.values())


def set_end_offsets(chunks):
    """분할기가 기록한 시작 위치와 청크 길이로 끝 위치를 갱신합니다."""
    for chunk in chunks:
        # end_index는 마지막 글자의 다음 위치입니다. Python 슬라이스와 같은 구간을 씁니다.
        chunk.metadata["end_index"] = chunk.metadata["start_index"] + len(chunk.page_content)

    return chunks


def add_pdf_pages(contexts, records_by_id):
    """본문의 문자 구간과 겹치는 PDF 시작·끝 페이지를 metadata에 붙입니다."""
    for context in contexts:
        meta = context.metadata
        record = records_by_id[meta["source_id"]]

        # 페이지 경계가 청크 경계와 다르므로 겹치는 모든 페이지를 찾습니다.
        pages = [
            span["pdf_page"] for span in record["page_spans"]
            if span["start"] < span["end"]
            and span["start"] < meta["end_index"] and meta["start_index"] < span["end"]
        ]
        meta["pdf_start_page"] = min(pages)
        meta["pdf_end_page"] = max(pages)

    return contexts
