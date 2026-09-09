package com.algamza.visionguard.ai;

import java.util.List;

// Names intentionally match the Python API's JSON contract.
public record PredictionResult(
        String frame_id, int image_width, int image_height,
        List<Detection> detections, List<Risk> risks,
        RiskLevel overall_risk, double processing_time_ms) {
    public enum RiskLevel { SAFE, WARNING, DANGER }
    public record BoundingBox(double x1, double y1, double x2, double y2) {}
    public record Detection(int class_id, String class_name, double confidence,
                            BoundingBox bbox, Integer track_id) {}
    public record Risk(RiskLevel level, int person_index, int forklift_index,
                       Integer person_track_id, Integer forklift_track_id,
                       double distance_px, double future_distance_px,
                       Double time_to_closest_approach_s, double score, String reason) {}
}
