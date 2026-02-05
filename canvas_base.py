import numpy as np
import OpenGL.GL as GL
from OpenGL.error import GLError  # 引入 GLError
from abc import abstractmethod
from PyQt5.QtWidgets import QOpenGLWidget

"""
Shared OpenGL helpers and the base canvas widget.
"""


def compile_shader(shader_src, shader_type):
    shader = GL.glCreateShader(shader_type)
    GL.glShaderSource(shader, shader_src)
    GL.glCompileShader(shader)
    status = GL.glGetShaderiv(shader, GL.GL_COMPILE_STATUS)
    if not status:
        msg = GL.glGetShaderInfoLog(shader)
        raise RuntimeError(msg)

    return shader


def create_program(vs, fs):
    vertex_shader = compile_shader(vs, GL.GL_VERTEX_SHADER)
    frag_shader = compile_shader(fs, GL.GL_FRAGMENT_SHADER)
    program = GL.glCreateProgram()
    GL.glAttachShader(program, vertex_shader)
    GL.glAttachShader(program, frag_shader)
    GL.glLinkProgram(program)
    status = GL.glGetProgramiv(program, GL.GL_LINK_STATUS)
    if not status:
        msg = GL.glGetProgramInfoLog(program)
        raise RuntimeError(msg)

    return program


def create_vao(v_pos, uv_coord):
    vao = GL.glGenVertexArrays(1)
    vbo = GL.glGenBuffers(1)
    uvbo = GL.glGenBuffers(1)
    GL.glBindVertexArray(vao)
    GL.glBindBuffer(GL.GL_ARRAY_BUFFER, vbo)
    GL.glBufferData(GL.GL_ARRAY_BUFFER, v_pos.nbytes, v_pos, GL.GL_DYNAMIC_DRAW)
    GL.glVertexAttribPointer(0, 2, GL.GL_FLOAT, False, 0, None)
    GL.glEnableVertexAttribArray(0)
    GL.glBindBuffer(GL.GL_ARRAY_BUFFER, uvbo)
    GL.glBufferData(GL.GL_ARRAY_BUFFER, uv_coord.nbytes, uv_coord, GL.GL_DYNAMIC_DRAW)
    GL.glVertexAttribPointer(1, 2, GL.GL_FLOAT, False, 0, None)
    GL.glEnableVertexAttribArray(1)
    GL.glBindBuffer(GL.GL_ARRAY_BUFFER, 0)
    GL.glBindVertexArray(0)
    return vao


def create_canvas_framebuffer(width, height):
    old_fbo = int(GL.glGetIntegerv(GL.GL_FRAMEBUFFER_BINDING))
    fbo = GL.glGenFramebuffers(1)
    # PyOpenGL 有时返回数组，有时返回整数，强制转换为 int 以防万一
    if isinstance(fbo, np.ndarray):
        fbo = int(fbo[0])
    else:
        fbo = int(fbo)

    GL.glBindFramebuffer(GL.GL_FRAMEBUFFER, fbo)

    texture = int(GL.glGenTextures(1))
    GL.glBindTexture(GL.GL_TEXTURE_2D, texture)
    GL.glTexImage2D(
        GL.GL_TEXTURE_2D,
        0,
        GL.GL_RGBA,
        width,
        height,
        0,
        GL.GL_RGBA,
        GL.GL_UNSIGNED_BYTE,
        None,
    )
    GL.glTexParameteri(GL.GL_TEXTURE_2D, GL.GL_TEXTURE_MIN_FILTER, GL.GL_LINEAR)
    GL.glTexParameteri(GL.GL_TEXTURE_2D, GL.GL_TEXTURE_MAG_FILTER, GL.GL_LINEAR)
    GL.glTexParameteri(GL.GL_TEXTURE_2D, GL.GL_TEXTURE_WRAP_S, GL.GL_CLAMP_TO_EDGE)
    GL.glTexParameteri(GL.GL_TEXTURE_2D, GL.GL_TEXTURE_WRAP_T, GL.GL_CLAMP_TO_EDGE)
    GL.glFramebufferTexture2D(
        GL.GL_FRAMEBUFFER,
        GL.GL_COLOR_ATTACHMENT0,
        GL.GL_TEXTURE_2D,
        texture,
        0,
    )

    GL.glBindFramebuffer(GL.GL_FRAMEBUFFER, old_fbo)
    return fbo, texture


class OpenGLCanvas(QOpenGLWidget):
    """Base canvas with offscreen framebuffer and opacity control."""

    def __init__(self):
        super().__init__()
        self._canvas_opacity = 1.0

    def _create_program(self):
        vertex_shader = """#version 330 core
        layout(location = 0) in vec2 a_position;
        layout(location = 1) in vec2 a_texCoord;
        out vec2 v_texCoord;
        void main() {
            gl_Position = vec4(a_position, 0.0, 1.0);
            v_texCoord = a_texCoord;
        }
        """
        frag_shader = """#version 330 core
        in vec2 v_texCoord;
        uniform sampler2D canvas;
        uniform float opacity;
        void main() {
            vec4 color = texture(canvas, v_texCoord);
            color *= opacity;
            gl_FragColor =  color;
        }
        """
        self._program = create_program(vertex_shader, frag_shader)
        self._opacity_loc = GL.glGetUniformLocation(self._program, "opacity")

    def _create_vao(self):
        vertices = np.array(
            [
                -1,
                1,
                -1,
                -1,
                1,
                -1,
                -1,
                1,
                1,
                -1,
                1,
                1,
            ],
            dtype=np.float32,
        )
        uvs = np.array(
            [
                0,
                1,
                0,
                0,
                1,
                0,
                0,
                1,
                1,
                0,
                1,
                1,
            ],
            dtype=np.float32,
        )
        self._vao = create_vao(vertices, uvs)

    def _create_canvas_framebuffer(self):
        # 使用物理像素大小创建 Framebuffer，支持高 DPI 清晰显示
        dpr = self.devicePixelRatioF() if hasattr(self, 'devicePixelRatioF') else float(self.devicePixelRatio())
        pixel_w = max(1, int(self.width() * dpr))
        pixel_h = max(1, int(self.height() * dpr))

        self._canvas_framebuffer, self._canvas_texture = create_canvas_framebuffer(
            pixel_w, pixel_h
        )

    def _draw_on_canvas(self):
        # Use Qt's default framebuffer object instead of querying OpenGL state directly
        old_fbo = self.defaultFramebufferObject()

        GL.glBindFramebuffer(GL.GL_FRAMEBUFFER, self._canvas_framebuffer)

        # 必须设置 Viewport 为 Framebuffer 的实际大小 (物理像素)
        dpr = self.devicePixelRatioF() if hasattr(self, 'devicePixelRatioF') else float(self.devicePixelRatio())
        frame_w = int(self.width() * dpr)
        frame_h = int(self.height() * dpr)
        GL.glViewport(0, 0, frame_w, frame_h)

        self.on_draw()

        try:
            GL.glBindFramebuffer(GL.GL_FRAMEBUFFER, old_fbo)
            # 恢复 Viewport 到窗口大小（避免影响后续 paintGL 的绘制）
            GL.glViewport(0, 0, frame_w, frame_h)
        except GLError as e:
            if e.err == 1282 or e.err == 1281: # 忽略 1281 GL_INVALID_VALUE 也是同样的状态问题
                # 忽略 GL_INVALID_OPERATION (1282) 和 GL_INVALID_VALUE (1281)
                # 这通常是 Qt 和 PyOpenGL 状态同步的误报，不影响实际渲染
                pass
            else:
                print(f"OpenGL Error restoring framebuffer {old_fbo}: {e}")
        except Exception as e:
            print(f"Error restoring framebuffer {old_fbo}: {e}")

    def initializeGL(self):
        self._create_program()
        self._create_vao()
        self._create_canvas_framebuffer()
        self.on_init()

    def resizeGL(self, w, h):
        # Delete old framebuffer and texture
        if hasattr(self, '_canvas_framebuffer'):
             GL.glDeleteFramebuffers(1, [self._canvas_framebuffer])
        if hasattr(self, '_canvas_texture'):
             GL.glDeleteTextures(1, [self._canvas_texture])

        # Recreate framebuffer with new size
        self._create_canvas_framebuffer()

        # Notify child class
        self.on_resize(w, h)

    def paintGL(self):
        self._draw_on_canvas()
        GL.glClearColor(0.0, 0.0, 0.0, 0.0)
        GL.glClear(GL.GL_COLOR_BUFFER_BIT)
        GL.glBindVertexArray(self._vao)
        GL.glUseProgram(self._program)
        GL.glProgramUniform1f(self._program, self._opacity_loc, self._canvas_opacity)
        GL.glActiveTexture(GL.GL_TEXTURE0)
        GL.glBindTexture(GL.GL_TEXTURE_2D, self._canvas_texture)
        GL.glDrawArrays(GL.GL_TRIANGLES, 0, 6)
        GL.glBindVertexArray(0)

    def setCanvasOpacity(self, value: float):
        self._canvas_opacity = value

    @abstractmethod
    def on_init(self):
        ...

    @abstractmethod
    def on_draw(self):
        ...

    @abstractmethod
    def on_resize(self, width: int, height: int):
        ...
