// Selection coordinates refer to original image pixels, not preview pixels.
class RectangleSelection {
  constructor(stage, image, overlay, onChange) {
    this.stage = stage;
    this.image = image;
    this.overlay = overlay;
    this.onChange = onChange;
    this.box = null;
    this.active = false;
    this.pointer = null;
    stage.addEventListener('pointerdown', e => this.start(e));
    stage.addEventListener('pointermove', e => this.move(e));
    stage.addEventListener('pointerup', e => this.finish(e));
    stage.addEventListener('pointercancel', () => this.cancelDrag());
    image.addEventListener('load', () => this.draw());
    this.resize = new ResizeObserver(() => this.draw());
    this.resize.observe(image);
  }
  setActive(active) {
    this.active = active;
    this.stage.classList.toggle('selecting', active);
    if (!active) this.cancelDrag();
  }
  clear() {
    this.setActive(false);
    this.box = null;
    this.draw();
  }
  point(event) {
    const r = this.image.getBoundingClientRect();
    return [Math.max(0, Math.min(this.image.naturalWidth, (event.clientX-r.left) / r.width * this.image.naturalWidth)),
            Math.max(0, Math.min(this.image.naturalHeight, (event.clientY-r.top) / r.height * this.image.naturalHeight))];
  }
  start(event) {
    if (!this.active || event.button !== 0 || this.pointer !== null || !this.image.naturalWidth) return;
    const r = this.image.getBoundingClientRect();
    if (event.clientX < r.left || event.clientX > r.right || event.clientY < r.top || event.clientY > r.bottom) return;
    event.preventDefault(); event.stopPropagation();
    this.pointer = event.pointerId;
    this.previous = this.box;
    this.origin = this.point(event);
    this.stage.setPointerCapture(event.pointerId);
  }
  move(event) {
    if (this.pointer !== event.pointerId) return;
    event.preventDefault();
    const p = this.point(event), o = this.origin;
    this.box = [Math.floor(Math.min(p[0],o[0])), Math.floor(Math.min(p[1],o[1])),
                Math.ceil(Math.max(p[0],o[0])), Math.ceil(Math.max(p[1],o[1]))];
    this.draw();
  }
  finish(event) {
    if (this.pointer !== event.pointerId) return;
    this.move(event);
    const id = this.pointer;
    this.pointer = null;
    if (this.stage.hasPointerCapture(id)) this.stage.releasePointerCapture(id);
    if (!this.box || this.box[2]-this.box[0] < 2 || this.box[3]-this.box[1] < 2) {
      this.box = this.previous;
      this.draw();
      return;
    }
    this.onChange(this.box);
  }
  cancelDrag() {
    if (this.pointer === null) return;
    const id = this.pointer;
    this.pointer = null;
    if (this.stage.hasPointerCapture(id)) this.stage.releasePointerCapture(id);
    this.box = this.previous;
    this.draw();
  }
  draw() {
    const box = this.box, r = this.image.getBoundingClientRect(), s = this.stage.getBoundingClientRect();
    this.overlay.hidden = !box || !r.width || !this.image.naturalWidth;
    if (this.overlay.hidden) return;
    const sx = r.width / this.image.naturalWidth, sy = r.height / this.image.naturalHeight;
    Object.assign(this.overlay.style, {
      left: `${r.left-s.left+box[0]*sx}px`, top: `${r.top-s.top+box[1]*sy}px`,
      width: `${(box[2]-box[0])*sx}px`, height: `${(box[3]-box[1])*sy}px`,
    });
  }
}
