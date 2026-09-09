package com.algamza.visionguard.ai;

public class AiUnavailableException extends RuntimeException {
    public AiUnavailableException() { super("AI 서버 응답을 받을 수 없습니다."); }
}
