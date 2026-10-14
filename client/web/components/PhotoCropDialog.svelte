<script>
  // Окно обрезки фото: снимок и рамка пропорции фото анкеты поверх него.
  // Рамку двигают, тянут за углы и меняют колесом мыши; «Сохранить» отдаёт
  // вырезанное картинкой. Рама, шапка и подвал — общие окна (`narrow`), как у
  // окна заведения по адресу.
  //
  // `ratio` — ширина к высоте рамки фото в анкете: вырезанное ложится туда
  // целиком, без полос и без обрезки.
  import { movedCrop, outputSize, resizedCrop, startCrop, zoomedCrop } from '$state/photo_crop.js';
  import ModalFoot from './ModalFoot.svelte';
  import ModalHead from './ModalHead.svelte';
  import ModalShell from './ModalShell.svelte';

  let { image, ratio, onsave, onclose } = $props();

  // Наибольшая сторона снимка в окне — по ширине коробки окна.
  const STAGE = 400;
  const OUTPUT = 900;
  const ZOOM_STEP = 1.1;
  const CORNERS = ['nw', 'ne', 'sw', 'se'];

  let picture = $state(null);
  let stage = $state(null);
  let size = $state(null);
  let crop = $state(null);
  let grip = null;

  const scale = $derived(size ? Math.min(STAGE / size.w, STAGE / size.h) : 1);

  function loaded() {
    size = { w: picture.naturalWidth, h: picture.naturalHeight };
    crop = startCrop(size.w, size.h, ratio);
  }

  /** Взяться за рамку (`corner` пусто) или за её угол. */
  function grab(event, corner = '') {
    event.stopPropagation();
    stage.setPointerCapture(event.pointerId);
    grip = { corner, x: event.clientX, y: event.clientY, crop };
  }

  function drag(event) {
    if (grip === null) return;
    const dx = (event.clientX - grip.x) / scale;
    const dy = (event.clientY - grip.y) / scale;
    crop = grip.corner
      ? resizedCrop(grip.crop, grip.corner, dx, dy, size.w, size.h, ratio)
      : movedCrop(grip.crop, dx, dy, size.w, size.h);
  }

  function zoom(event) {
    event.preventDefault();
    const factor = event.deltaY < 0 ? 1 / ZOOM_STEP : ZOOM_STEP;
    crop = zoomedCrop(crop, factor, size.w, size.h, ratio);
  }

  function save() {
    const out = outputSize(crop, OUTPUT);
    const canvas = document.createElement('canvas');
    canvas.width = out.w;
    canvas.height = out.h;
    canvas
      .getContext('2d')
      .drawImage(picture, crop.x, crop.y, crop.w, crop.h, 0, 0, canvas.width, canvas.height);
    onsave(canvas.toDataURL('image/jpeg', 0.92));
  }
</script>

<ModalShell extra="narrow photo-crop-dialog" {onclose} confirm={crop ? save : null}>
  {#snippet children()}
    <ModalHead icon="crop" title="Фото для анкеты" {onclose} />

    <div class="modal-body">
      <div
        class="crop-stage"
        role="presentation"
        bind:this={stage}
        style:width={size ? `${size.w * scale}px` : null}
        style:height={size ? `${size.h * scale}px` : null}
        onwheel={crop ? zoom : null}
        onpointermove={drag}
        onpointerup={() => (grip = null)}
        onlostpointercapture={() => (grip = null)}
      >
        <img bind:this={picture} src={image} alt="Снимок для обрезки" draggable="false" onload={loaded} />
        {#if crop}
          <div
            class="crop-box"
            role="presentation"
            style:left="{crop.x * scale}px"
            style:top="{crop.y * scale}px"
            style:width="{crop.w * scale}px"
            style:height="{crop.h * scale}px"
            onpointerdown={(event) => grab(event)}
          >
            {#each CORNERS as corner (corner)}
              <div
                class="crop-corner"
                data-corner={corner}
                role="presentation"
                onpointerdown={(event) => grab(event, corner)}
              ></div>
            {/each}
          </div>
        {/if}
      </div>
    </div>

    <ModalFoot
      label="Сохранить"
      ready={!!crop}
      oncancel={onclose}
      onconfirm={save}
    />
  {/snippet}
</ModalShell>
