package com.algamza.visionguard.config;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.config.annotation.CorsRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;
import java.util.Arrays;

@Configuration
public class WebConfig implements WebMvcConfigurer {
    private final String[] origins;
    public WebConfig(@Value("${visionguard.cors.allowed-origins:http://localhost:3000,http://localhost:5173}") String origins) {
        this.origins = Arrays.stream(origins.split(",")).map(String::trim)
                .filter(value -> !value.isEmpty()).toArray(String[]::new);
        if (Arrays.stream(this.origins).anyMatch(value -> value.contains("*")))
            throw new IllegalArgumentException("CORS에는 와일드카드 대신 프론트 origin을 지정하세요.");
    }
    @Override
    public void addCorsMappings(CorsRegistry registry) {
        registry.addMapping("/api/**").allowedOrigins(origins)
                .allowedMethods("GET", "POST", "OPTIONS")
                .allowedHeaders("Content-Type", "Accept")
                .allowCredentials(false).maxAge(3600);
    }
}
