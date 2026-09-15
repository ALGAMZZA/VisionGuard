export async function getUnityGroundTruth(url, options = {}) {
  const response = await fetch(`${url}?t=${Date.now()}`, {
    cache: 'no-store',
    signal: options.signal,
  });
  if (!response.ok) throw new Error(`Ground Truth HTTP ${response.status}`);
  return response.json();
}

function pixelBox(object, width, height) {
  const box = object?.bbox || {};
  const boxWidth = Number(box.width || 0) * width;
  const boxHeight = Number(box.height || 0) * height;
  const centerX = Number(box.x_center || 0) * width;
  const centerY = Number(box.y_center || 0) * height;
  return {
    x1: centerX - boxWidth / 2,
    y1: centerY - boxHeight / 2,
    x2: centerX + boxWidth / 2,
    y2: centerY + boxHeight / 2,
  };
}

function intersectionOverDetection(detectionBox, truthBox) {
  const x1 = Math.max(Number(detectionBox.x1), truthBox.x1);
  const y1 = Math.max(Number(detectionBox.y1), truthBox.y1);
  const x2 = Math.min(Number(detectionBox.x2), truthBox.x2);
  const y2 = Math.min(Number(detectionBox.y2), truthBox.y2);
  const intersection = Math.max(0, x2 - x1) * Math.max(0, y2 - y1);
  const detectionArea = Math.max(1, Number(detectionBox.x2) - Number(detectionBox.x1))
    * Math.max(1, Number(detectionBox.y2) - Number(detectionBox.y1));
  return intersection / detectionArea;
}

export function verifiedDetections(prediction, groundTruth) {
  const width = Number(prediction?.image_width) || 1280;
  const height = Number(prediction?.image_height) || 720;
  const detections = Array.isArray(prediction?.detections)
    ? prediction.detections.filter((detection) => !detection.is_predicted)
    : [];
  const objects = Array.isArray(groundTruth?.objects)
    ? groundTruth.objects.filter((object) => object.visible && ['person', 'forklift'].includes(String(object.class_name).toLowerCase()))
    : [];
  const used = new Set();

  return objects.flatMap((object) => {
    const truthBox = pixelBox(object, width, height);
    let bestIndex = -1;
    let bestOverlap = 0;
    detections.forEach((detection, index) => {
      if (used.has(index) || !detection.bbox) return;
      const overlap = intersectionOverDetection(detection.bbox, truthBox);
      if (overlap > bestOverlap) {
        bestOverlap = overlap;
        bestIndex = index;
      }
    });
    if (bestIndex < 0 || bestOverlap < 0.35) return [];
    used.add(bestIndex);
    const detection = detections[bestIndex];
    return [{
      ...detection,
      class_name: String(object.class_name).toLowerCase(),
      object_id: object.object_id,
      bbox: truthBox,
      local_position: object.local_position,
      global_position: object.global_position,
    }];
  });
}
