package com.algamza.visionguard;

import org.flywaydb.core.Flyway;
import org.flywaydb.core.api.FlywayException;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.springframework.core.io.ClassPathResource;
import org.springframework.core.io.ByteArrayResource;
import java.util.Map;
import java.nio.charset.StandardCharsets;
import org.springframework.jdbc.datasource.init.ScriptUtils;
import java.nio.file.Files;
import java.nio.file.Path;
import java.sql.DriverManager;
import java.util.UUID;
import static org.assertj.core.api.Assertions.*;

class DatabaseMigrationTests {
    @TempDir Path temp;

    String database() { return "jdbc:h2:mem:migration_" + UUID.randomUUID() + ";MODE=MySQL;DB_CLOSE_DELAY=-1"; }
    Flyway flyway(String url) {
        return Flyway.configure().dataSource(url, "sa", "").locations("classpath:db/migration")
                .placeholders(Map.of("instantType", "TIMESTAMP(6) WITH TIME ZONE", "jsonTextType", "CLOB"))
                .baselineOnMigrate(false).baselineVersion("1").cleanDisabled(true).load();
    }
    void legacySchema(String url) throws Exception {
        try (var connection = DriverManager.getConnection(url, "sa", "")) {
            String sql = new ClassPathResource("db/migration/V1__create_initial_schema.sql").getContentAsString(StandardCharsets.UTF_8)
                    .replace("${instantType}", "TIMESTAMP(6) WITH TIME ZONE").replace("${jsonTextType}", "CLOB");
            ScriptUtils.executeSqlScript(connection, new ByteArrayResource(sql.getBytes(StandardCharsets.UTF_8)));
            connection.createStatement().executeUpdate("""
                    INSERT INTO risk_events (camera_id, frame_id, captured_at, created_at, level, prediction_json)
                    VALUES ('camera-1', 'preserved', '2026-09-07 00:00:00', '2026-09-07 00:00:00', 'WARNING', '{"keep":"unchanged"}')
                    """);
        }
    }
    void assertDataPreserved(String url) throws Exception {
        try (var connection = DriverManager.getConnection(url, "sa", "");
             var result = connection.createStatement().executeQuery("SELECT frame_id, prediction_json, stream_id FROM risk_events")) {
            assertThat(result.next()).isTrue();
            assertThat(result.getString(1)).isEqualTo("preserved");
            assertThat(result.getString(2)).isEqualTo("{\"keep\":\"unchanged\"}");
            assertThat(result.getString(3)).isNull();
            assertThat(result.next()).isFalse();
        }
    }

    @Test void emptyDatabaseRunsV1AndSecondRunDoesNothing() {
        var flyway = flyway(database());
        assertThat(flyway.migrate().migrationsExecuted).isEqualTo(1);
        assertThat(flyway.info().current().getVersion().getVersion()).isEqualTo("1");
        assertThat(flyway.migrate().migrationsExecuted).isZero();
        flyway.validate();
    }

    @Test void existingUnmanagedDatabaseIsRejectedWithoutChangingData() throws Exception {
        String url = database();
        legacySchema(url);
        assertThatThrownBy(() -> flyway(url).migrate()).isInstanceOf(FlywayException.class)
                .hasMessageContaining("non-empty");
        assertDataPreserved(url);
    }

    @Test void explicitBaselinePreservesExistingRowsAndAllowsNormalStartup() throws Exception {
        String url = database();
        legacySchema(url);
        flyway(url).baseline();
        var normal = flyway(url);
        assertThat(normal.migrate().migrationsExecuted).isZero();
        assertThat(normal.info().current().getType().name()).isEqualTo("BASELINE");
        normal.validate();
        assertDataPreserved(url);
    }

    @Test void changingAnAppliedSqlIsRejected() throws Exception {
        String url = database();
        Path sql = temp.resolve("V1__create_initial_schema.sql");
        String original = new ClassPathResource("db/migration/V1__create_initial_schema.sql").getContentAsString(java.nio.charset.StandardCharsets.UTF_8);
        Files.writeString(sql, original);
        Flyway.configure().dataSource(url, "sa", "").locations("filesystem:" + temp)
                .placeholders(Map.of("instantType", "TIMESTAMP(6) WITH TIME ZONE", "jsonTextType", "CLOB")).load().migrate();
        Files.writeString(sql, original + "\nCREATE TABLE unexpected_change (id INT);\n");
        var changed = Flyway.configure().dataSource(url, "sa", "").locations("filesystem:" + temp)
                .placeholders(Map.of("instantType", "TIMESTAMP(6) WITH TIME ZONE", "jsonTextType", "CLOB")).load();
        assertThatThrownBy(changed::migrate).isInstanceOf(FlywayException.class).hasMessageContaining("checksum");
    }

    @Test void cleanIsDisabled() {
        var flyway = flyway(database());
        flyway.migrate();
        assertThatThrownBy(flyway::clean).isInstanceOf(FlywayException.class);
        assertThat(flyway.info().current()).isNotNull();
    }
}
