package com.algamza.visionguard.config;

import io.swagger.v3.oas.models.OpenAPI;
import io.swagger.v3.oas.models.info.Info;
import io.swagger.v3.oas.models.servers.Server;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import java.util.List;

@Configuration
public class OpenApiConfig {
    @Bean
    OpenAPI visionGuardApi() {
        return new OpenAPI().info(new Info().title("VisionGuard Backend API").version("1.0")
                .description("단일 카메라 프레임 분석, 위험 이력 조회 및 영상 종료 API. "
                        + "기본 AI 모드는 mock(고정 WARNING)입니다. Try it out의 POST 요청은 실제 DB에 기록됩니다. "
                        + "같은 영상은 동일 streamId로 프레임을 순서대로 보내고 종료 API를 호출하세요."))
                .servers(List.of(new Server().url("/").description("현재 백엔드 서버")));
    }
}
