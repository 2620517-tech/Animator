"""Sketch Animator — MVP (AI 없이 동작하는 키프레임 애니메이션 골격)"""

import io

import streamlit as st
from PIL import Image, ImageDraw, ImageFont

try:
    from streamlit_drawable_canvas import st_canvas
    HAS_CANVAS = True
except Exception:
    HAS_CANVAS = False

FIELDS = ("x", "y", "w", "h", "rot")


def init_state():
    ss = st.session_state
    ss.setdefault("canvas_w", 512)
    ss.setdefault("canvas_h", 512)
    ss.setdefault("total_frames", 24)
    ss.setdefault("fps", 12)
    ss.setdefault("current_frame", 0)
    ss.setdefault("boxes", [])
    ss.setdefault("selected_box_id", None)
    ss.setdefault("next_box_id", 1)
    ss.setdefault("tx", 256)
    ss.setdefault("ty", 256)
    ss.setdefault("tw", 120)
    ss.setdefault("th", 120)
    ss.setdefault("trot", 0)


def get_selected_box():
    for b in st.session_state.boxes:
        if b["id"] == st.session_state.selected_box_id:
            return b
    return None


def add_box():
    ss = st.session_state
    bid = ss.next_box_id
    ss.next_box_id += 1
    palette = ["#4C9AFF", "#FF6B6B", "#51CF66", "#FFD43B", "#CC5DE8", "#FF922B"]
    ss.boxes.append({
        "id": bid,
        "name": f"Box {bid}",
        "prompt": "",
        "color": palette[(bid - 1) % len(palette)],
        "sketch_png": None,
        "ai_image": None,
        "keyframes": [],
    })
    ss.selected_box_id = bid


def delete_box(box_id):
    ss = st.session_state
    ss.boxes = [b for b in ss.boxes if b["id"] != box_id]
    if ss.selected_box_id == box_id:
        ss.selected_box_id = ss.boxes[0]["id"] if ss.boxes else None


def transform_at(box, frame):
    kfs = sorted(box["keyframes"], key=lambda k: k["frame"])
    if not kfs:
        return None
    if frame <= kfs[0]["frame"]:
        return {f: kfs[0][f] for f in FIELDS}
    if frame >= kfs[-1]["frame"]:
        return {f: kfs[-1][f] for f in FIELDS}
    for a, b in zip(kfs, kfs[1:]):
        if a["frame"] <= frame <= b["frame"]:
            span = b["frame"] - a["frame"]
            t = 0.0 if span == 0 else (frame - a["frame"]) / span
            return {f: a[f] + (b[f] - a[f]) * t for f in FIELDS}
    return {f: kfs[-1][f] for f in FIELDS}


def set_keyframe(box, frame, transform):
    for kf in box["keyframes"]:
        if kf["frame"] == frame:
            kf.update(transform)
            return
    box["keyframes"].append({"frame": frame, **transform})


def delete_keyframe(box, frame):
    box["keyframes"] = [k for k in box["keyframes"] if k["frame"] != frame]


def _hex_to_rgb(hex_color):
    hex_color = hex_color.lstrip("#")
    return tuple(int(hex_color[i:i + 2], 16) for i in (0, 2, 4))


def render_frame(boxes, frame, size, show_labels=True):
    W, H = size
    img = Image.new("RGBA", (W, H), (255, 255, 255, 255))
    try:
        font = ImageFont.load_default()
    except Exception:
        font = None

    for box in boxes:
        t = transform_at(box, frame)
        if t is None:
            continue
        w = max(1, int(round(t["w"])))
        h = max(1, int(round(t["h"])))
        layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        d = ImageDraw.Draw(layer)
        r, g, b = _hex_to_rgb(box["color"])

        # === AI 연동 지점: box["ai_image"]가 있으면 그걸, 없으면 색칠 사각형 ===
        if box.get("ai_image") is not None:
            layer.alpha_composite(box["ai_image"].convert("RGBA").resize((w, h)))
        else:
            d.rectangle([0, 0, w - 1, h - 1], fill=(r, g, b, 200),
                        outline=(30, 30, 30, 255), width=2)

        if show_labels and font is not None:
            d.text((4, 4), box["name"], fill=(20, 20, 20, 255), font=font)

        rotated = layer.rotate(t["rot"], expand=True, resample=Image.BICUBIC)
        cx, cy = int(round(t["x"])), int(round(t["y"]))
        img.alpha_composite(rotated, (cx - rotated.width // 2, cy - rotated.height // 2))

    return img.convert("RGB")


def export_gif(boxes, total, size, fps):
    frames = [render_frame(boxes, f, size, show_labels=False) for f in range(max(1, total))]
    buf = io.BytesIO()
    duration = max(1, int(round(1000 / max(1, fps))))
    frames[0].save(buf, format="GIF", save_all=True, append_images=frames[1:],
                   duration=duration, loop=0, disposal=2)
    return buf.getvalue()


def sidebar():
    ss = st.session_state
    with st.sidebar:
        st.header("🎬 프로젝트 설정")
        ss.canvas_w = st.number_input("캔버스 너비", 64, 2048, ss.canvas_w, step=32)
        ss.canvas_h = st.number_input("캔버스 높이", 64, 2048, ss.canvas_h, step=32)
        ss.total_frames = st.number_input("총 프레임 수", 1, 600, ss.total_frames)
        ss.fps = st.number_input("FPS", 1, 60, ss.fps)

        st.divider()
        st.header("📦 상자 목록")
        if st.button("➕ 새 상자 추가", use_container_width=True):
            add_box()

        if not ss.boxes:
            st.caption("상자가 없습니다. 새 상자를 추가하세요.")
        for b in ss.boxes:
            cols = st.columns([5, 1])
            mark = "🔹" if b["id"] == ss.selected_box_id else "▫️"
            if cols[0].button(f"{mark} {b['name']} ({len(b['keyframes'])} kf)",
                              key=f"sel_{b['id']}", use_container_width=True):
                ss.selected_box_id = b["id"]
            if cols[1].button("🗑", key=f"del_{b['id']}"):
                delete_box(b["id"])
                st.rerun()


def box_settings(box):
    st.subheader("📝 상자 속성")
    c1, c2 = st.columns(2)
    box["name"] = c1.text_input("이름", box["name"], key=f"name_{box['id']}")
    box["color"] = c2.color_picker("색상 (placeholder)", box["color"], key=f"color_{box['id']}")
    box["prompt"] = st.text_area("프롬프트 / 코멘트 (그림 AI에게 줄 묘사)", box["prompt"],
                                 key=f"prompt_{box['id']}",
                                 placeholder="예) a small red robot, side view, flat cartoon style",
                                 height=80)

    with st.expander("✏️ 스케치 (선택 — 나중에 AI 입력으로 사용)"):
        if HAS_CANVAS:
            res = st_canvas(fill_color="rgba(0,0,0,0)", stroke_width=3, stroke_color="#000000",
                            background_color="#FFFFFF", height=200, width=200,
                            drawing_mode="freedraw", key=f"canvas_{box['id']}")
            if res is not None and res.image_data is not None:
                im = Image.fromarray(res.image_data.astype("uint8"), "RGBA")
                buf = io.BytesIO()
                im.save(buf, format="PNG")
                box["sketch_png"] = buf.getvalue()
        else:
            st.info("스케치 캔버스를 쓰려면 `pip install streamlit-drawable-canvas` 후 다시 실행하세요.")


def keyframe_editor(box):
    ss = st.session_state
    st.subheader("🎞 키프레임 편집기")
    ss.current_frame = st.slider("현재 프레임", 0, max(0, ss.total_frames - 1),
                                 min(ss.current_frame, ss.total_frames - 1))

    st.markdown("**작업용 트랜스폼** (슬라이더로 정하고 → 키프레임으로 저장)")
    c1, c2 = st.columns(2)
    ss.tx = c1.slider("X 위치", 0, ss.canvas_w, int(ss.tx), key="s_tx")
    ss.ty = c2.slider("Y 위치", 0, ss.canvas_h, int(ss.ty), key="s_ty")
    ss.tw = c1.slider("너비", 1, ss.canvas_w, int(ss.tw), key="s_tw")
    ss.th = c2.slider("높이", 1, ss.canvas_h, int(ss.th), key="s_th")
    ss.trot = st.slider("회전(방향, °)", -180, 180, int(ss.trot), key="s_trot")

    cur_t = {"x": ss.tx, "y": ss.ty, "w": ss.tw, "h": ss.th, "rot": ss.trot}

    b1, b2, b3 = st.columns(3)
    if b1.button("💾 현재 프레임에 키프레임 저장", use_container_width=True):
        set_keyframe(box, ss.current_frame, cur_t)
        st.toast(f"프레임 {ss.current_frame}에 키프레임 저장")
    if b2.button("📥 현재 프레임 값 불러오기", use_container_width=True):
        t = transform_at(box, ss.current_frame)
        if t:
            ss.tx, ss.ty, ss.tw, ss.th, ss.trot = (int(t["x"]), int(t["y"]),
                                                   int(t["w"]), int(t["h"]), int(t["rot"]))
            st.rerun()
        else:
            st.toast("키프레임이 아직 없습니다.")
    if b3.button("🗑 현재 프레임 키프레임 삭제", use_container_width=True):
        delete_keyframe(box, ss.current_frame)
        st.toast(f"프레임 {ss.current_frame} 키프레임 삭제")

    if box["keyframes"]:
        st.caption("저장된 키프레임: " + ", ".join(str(k["frame"]) for k in sorted(box["keyframes"], key=lambda x: x["frame"])))
    else:
        st.caption("아직 키프레임이 없습니다. 최소 2개를 만들면 보간이 시작됩니다.")


def preview_and_export():
    ss = st.session_state
    size = (ss.canvas_w, ss.canvas_h)
    st.subheader("👁 미리보기")
    st.image(render_frame(ss.boxes, ss.current_frame, size, show_labels=True),
             caption=f"프레임 {ss.current_frame} / {ss.total_frames - 1}")

    st.divider()
    st.subheader("📤 내보내기")
    if st.button("🎞 GIF 생성", use_container_width=True):
        if not ss.boxes or all(len(b["keyframes"]) == 0 for b in ss.boxes):
            st.warning("키프레임이 있는 상자가 필요합니다.")
        else:
            with st.spinner("렌더링 중..."):
                gif_bytes = export_gif(ss.boxes, ss.total_frames, size, ss.fps)
            st.image(gif_bytes, caption="결과 애니메이션")
            st.download_button("⬇️ GIF 다운로드", gif_bytes, file_name="animation.gif",
                               mime="image/gif", use_container_width=True)


def main():
    st.set_page_config(page_title="Sketch Animator", page_icon="🎬", layout="wide")
    init_state()
    st.title("🎬 Sketch Animator — MVP")
    st.caption("슬라이더로 상자를 움직여 키프레임을 만들면, 사이 프레임은 자동 선형보간됩니다. (그림 AI는 추후 연동)")
    sidebar()

    box = get_selected_box()
    if box is None:
        st.info("⬅️ 사이드바에서 **새 상자 추가**를 눌러 시작하세요.")
        return

    left, right = st.columns([1, 1])
    with left:
        box_settings(box)
        keyframe_editor(box)
    with right:
        preview_and_export()


if __name__ == "__main__":
    main()