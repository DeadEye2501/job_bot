// Рамка обрезки фото в точках самого снимка: где встаёт, куда ходит, как растёт.
//
// Чистые функции: числа на вход, рамка на выход. Рамка всегда целиком внутри
// снимка и в пропорции рамки фото в анкете — иначе в анкете остались бы пустые
// полосы или снимок вытянулся бы.

import { clamp } from './bounds.js';

/** Самая большая рамка нужной пропорции посередине снимка. */
export function startCrop(width, height, ratio) {
  if (width / height > ratio) {
    const w = height * ratio;
    return { x: (width - w) / 2, y: 0, w, h: height };
  }
  const h = width / ratio;
  return { x: 0, y: (height - h) / 2, w: width, h };
}

/** Рамка, сдвинутая на столько точек снимка, но не дальше его краёв. */
export function movedCrop(crop, dx, dy, width, height) {
  return {
    ...crop,
    x: clamp(crop.x + dx, 0, width - crop.w),
    y: clamp(crop.y + dy, 0, height - crop.h),
  };
}

/** Рамка, выросшая или сжавшаяся вокруг своей середины; больше самой большой
 *  не растёт. */
export function zoomedCrop(crop, factor, width, height, ratio) {
  const largest = startCrop(width, height, ratio);
  const w = clamp(crop.w * factor, smallest(largest), largest.w);
  const h = w / ratio;
  return {
    x: clamp(crop.x + crop.w / 2 - w / 2, 0, width - w),
    y: clamp(crop.y + crop.h / 2 - h / 2, 0, height - h),
    w,
    h,
  };
}

/** Рамка, растянутая за угол: противоположный угол стоит на месте.
 *
 * `corner` — тянутый угол: `nw`, `ne`, `sw`, `se`. Пропорция держится, поэтому
 * размер задаёт одна ось — та, по которой тянут сильнее.
 * Растёт рамка до края снимка со стороны угла и сжимается до той же десятой
 * доли, что и колесом.
 */
export function resizedCrop(crop, corner, dx, dy, width, height, ratio) {
  const east = corner.endsWith('e');
  const south = corner.startsWith('s');
  const anchorX = east ? crop.x : crop.x + crop.w;
  const anchorY = south ? crop.y : crop.y + crop.h;
  const roomW = Math.min(east ? width - anchorX : anchorX, (south ? height - anchorY : anchorY) * ratio);
  const byX = east ? dx : -dx;
  const byY = (south ? dy : -dy) * ratio;
  const change = Math.abs(byX) >= Math.abs(byY) ? byX : byY;
  const w = clamp(crop.w + change, smallest(startCrop(width, height, ratio)), roomW);
  const h = w / ratio;
  return { x: east ? anchorX : anchorX - w, y: south ? anchorY : anchorY - h, w, h };
}

/** Размер вырезанного снимка: не больше `limit` по большей стороне — больше
 *  рамке анкеты и сайтам не нужно, — а мелкое не растягивается. */
export function outputSize(crop, limit) {
  const shrink = Math.min(1, limit / Math.max(crop.w, crop.h));
  return { w: Math.round(crop.w * shrink), h: Math.round(crop.h * shrink) };
}

/** Меньше десятой доли самой большой рамки не сжимается: из такой полоски в
 *  анкете остались бы одни точки. */
function smallest(largest) {
  return largest.w / 10;
}
