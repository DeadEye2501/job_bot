// Рамка обрезки фото: где она встаёт, куда ходит и как растёт.
//
// Предмет — числа рамки в точках самого снимка: из них окно вырезает фото,
// и рамка, вышедшая за снимок, дала бы пустые полосы в анкете.

import { describe, expect, it } from 'vitest';

import { movedCrop, outputSize, resizedCrop, startCrop, zoomedCrop } from '../state/photo_crop.js';

const RATIO = 3 / 4;

describe('рамка обрезки', () => {
  it('на высоком снимке встаёт во всю ширину посередине по высоте', () => {
    expect(startCrop(300, 1000, RATIO)).toEqual({ x: 0, y: 300, w: 300, h: 400 });
  });

  it('на широком снимке встаёт во всю высоту посередине по ширине', () => {
    expect(startCrop(1000, 400, RATIO)).toEqual({ x: 350, y: 0, w: 300, h: 400 });
  });

  it('сдвигается, но не выходит за снимок', () => {
    const crop = { x: 0, y: 300, w: 300, h: 400 };

    expect(movedCrop(crop, 50, -100, 300, 1000)).toEqual({ x: 0, y: 200, w: 300, h: 400 });
    expect(movedCrop(crop, 0, 900, 300, 1000)).toEqual({ x: 0, y: 600, w: 300, h: 400 });
  });

  it('уменьшается вокруг своей середины и держит пропорцию', () => {
    const crop = { x: 0, y: 300, w: 300, h: 400 };

    expect(zoomedCrop(crop, 0.5, 300, 1000, RATIO)).toEqual({ x: 75, y: 400, w: 150, h: 200 });
  });

  it('за нижний правый угол растёт от верхнего левого, держа пропорцию', () => {
    const crop = { x: 0, y: 0, w: 150, h: 200 };

    expect(resizedCrop(crop, 'se', 75, 0, 300, 1000, RATIO)).toEqual({ x: 0, y: 0, w: 225, h: 300 });
  });

  it('за верхний левый угол сжимается к нижнему правому', () => {
    const crop = { x: 0, y: 300, w: 300, h: 400 };

    expect(resizedCrop(crop, 'nw', 150, 0, 300, 1000, RATIO)).toEqual({ x: 150, y: 500, w: 150, h: 200 });
  });

  it('растягиваясь за угол, не выходит за снимок', () => {
    const crop = { x: 0, y: 0, w: 150, h: 200 };

    expect(resizedCrop(crop, 'se', 1000, 1000, 300, 1000, RATIO)).toEqual({ x: 0, y: 0, w: 300, h: 400 });
  });

  it('вырезанное уменьшается до предела по большей стороне, мелкое — нет', () => {
    expect(outputSize({ x: 0, y: 0, w: 1500, h: 2000 }, 900)).toEqual({ w: 675, h: 900 });
    expect(outputSize({ x: 0, y: 0, w: 300, h: 400 }, 900)).toEqual({ w: 300, h: 400 });
  });

  it('не растёт больше снимка', () => {
    const crop = { x: 75, y: 400, w: 150, h: 200 };

    expect(zoomedCrop(crop, 10, 300, 1000, RATIO)).toEqual({ x: 0, y: 300, w: 300, h: 400 });
  });
});
