import argparse
import os
import torch
from torch import nn
import torchvision.transforms as TVT
import torchvision.transforms.functional as TVF
from PIL import Image, ImageColor

# Get cpu, gpu or mps device for training.
device = (
    "cuda"
    if torch.cuda.is_available()
    else "mps"
    if torch.backends.mps.is_available()
    else "cpu"
)

def align_up(value, align):
    return value + (align - value % align) % align

class UpConv_7(nn.Module):
    def __init__(self):
        super().__init__()
        self.padding = 14
        m = [nn.Conv2d(1, 16, 3, 1, 0),
             nn.LeakyReLU(0.1, inplace=True),
             nn.Conv2d(16, 32, 3, 1, 0),
             nn.LeakyReLU(0.1, inplace=True),
             nn.Conv2d(32, 64, 3, 1, 0),
             nn.LeakyReLU(0.1, inplace=True),
             nn.Conv2d(64, 128, 3, 1, 0),
             nn.LeakyReLU(0.1, inplace=True),
             nn.Conv2d(128, 128, 3, 1, 0),
             nn.LeakyReLU(0.1, inplace=True),
             nn.Conv2d(128, 256, 3, 1, 0),
             nn.LeakyReLU(0.1, inplace=True),
             nn.ConvTranspose2d(256, 1, 4, 2, 3),
             ]
        self.Sequential = nn.Sequential(*m)
        for m in self.modules():
            if isinstance(m, (nn.Conv2d, nn.ConvTranspose2d)):
                nn.init.kaiming_normal_(m.weight, mode='fan_out', nonlinearity='relu')
                if m.bias is not None:
                    nn.init.constant_(m.bias, 0)

    def forward(self, x):
        return self.Sequential.forward(x)

class UpConv_7_KanjiV2(nn.Module):
    def __init__(self):
        super().__init__()
        self.padding = 16+14

        feature = [nn.Conv2d(1, 16, 3, 1, 0),
             nn.LeakyReLU(0.1, inplace=True),
             nn.Conv2d(16, 64, 4, 1, 0),
             nn.LeakyReLU(0.1, inplace=True),
             nn.MaxPool2d(4),
             nn.Conv2d(64, 256, 5, 1, 0),
             nn.LeakyReLU(0.1),
             nn.Upsample(scale_factor=4, mode="bilinear"),
             ]
        self.Feature = nn.Sequential(*feature)

        main = [nn.Conv2d(3, 24, 3, 1, 0),
             nn.LeakyReLU(0.1, inplace=True),
             nn.Conv2d(24, 32, 3, 1, 0),
             nn.LeakyReLU(0.1, inplace=True),
             nn.Conv2d(32, 64, 3, 1, 0),
             nn.LeakyReLU(0.1, inplace=True),
             nn.Conv2d(64, 128, 3, 1, 0),
             nn.LeakyReLU(0.1, inplace=True),
             ]
        self.Main = nn.Sequential(*main)

        upscale = [
             nn.Conv2d(128+256, 256, 3, 1, 0),
             nn.LeakyReLU(0.1, inplace=True),
             nn.Conv2d(256, 256, 3, 1, 0),
             nn.LeakyReLU(0.1, inplace=True),
             nn.ConvTranspose2d(256, 1, 4, 2, 3),
             nn.Tanh(),
             ]
        self.Upscale = nn.Sequential(*upscale)

        for m in self.modules():
            if isinstance(m, (nn.Conv2d, nn.ConvTranspose2d)):
                nn.init.kaiming_normal_(m.weight, mode='fan_out', nonlinearity='leaky_relu', a=0.1)
                if m.bias is not None:
                    nn.init.constant_(m.bias, 0)

    def forward(self, x):
        feat = self.Feature.forward(x)

        x = torch.ones_like(x) - x
        v = x[:, :, 8:-8, 8:-8]
        dy = torch.diff(x[:, :, 8:-7, 8:-8], dim=2)
        dx = torch.diff(x[:, :, 8:-8, 8:-7], dim=3)

        vs = torch.cat([v, dy, dx], 1)

        main = self.Main.forward(vs)

        up_in = torch.cat([main, feat], 1)

        y = self.Upscale.forward(up_in)
        y = torch.ones_like(y) * 0.5 - y * 0.55
        return y

def lerp(a, b, t):
    return a*(1.0 - t) + b*t

def gradient(src, dst):
    src = ImageColor.getrgb(src)
    dst = ImageColor.getrgb(dst)
    return [int(lerp(src[c], dst[c], t/255.0)) for c in range(3) for t in range(256)]

class UpSelect_7(nn.Module):
    def __init__(self):
        super().__init__()
        self.padding = 14
        m = [nn.Conv2d(1, 16, 3, 1, 0),
             nn.LeakyReLU(0.1, inplace=True),
             nn.Conv2d(16, 32, 3, 1, 0),
             nn.LeakyReLU(0.1, inplace=True),
             nn.Conv2d(32, 64, 3, 1, 0),
             nn.LeakyReLU(0.1, inplace=True),
             nn.Conv2d(64, 128, 3, 1, 0),
             nn.LeakyReLU(0.1, inplace=True),
             nn.Conv2d(128, 128, 3, 1, 0),
             nn.LeakyReLU(0.1, inplace=True),
             nn.Conv2d(128, 256, 3, 1, 0),
             nn.LeakyReLU(0.1, inplace=True),
             nn.ConvTranspose2d(256, 1, 4, 2, 3),
             nn.Tanh(),
             ]
        self.Sequential = nn.Sequential(*m)
        for m in self.modules():
            if isinstance(m, (nn.Conv2d, nn.ConvTranspose2d)):
                nn.init.kaiming_normal_(m.weight, mode='fan_out', nonlinearity='relu')
                if m.bias is not None:
                    nn.init.constant_(m.bias, 0)

    def forward(self, x):
        x = torch.ones_like(x) - x
        y = self.Sequential.forward(x)
        y = torch.ones_like(y) * 0.5 - y * 0.55
        return y

class UpSelect_7_V2(nn.Module):
    def __init__(self):
        super().__init__()
        self.padding = 14
        m = [nn.Conv2d(1, 16, 3, 1, 0),
             nn.LeakyReLU(0.1, inplace=True),
             nn.Conv2d(16, 32, 3, 1, 0),
             nn.LeakyReLU(0.1, inplace=True),
             nn.Conv2d(32, 64, 3, 1, 0),
             nn.LeakyReLU(0.1, inplace=True),
             nn.Conv2d(64, 128, 3, 1, 0),
             nn.LeakyReLU(0.1, inplace=True),
             nn.Conv2d(128, 128, 3, 1, 0),
             nn.LeakyReLU(0.1, inplace=True),
             nn.Conv2d(128, 256, 3, 1, 0),
             nn.LeakyReLU(0.1, inplace=True),
             nn.ConvTranspose2d(256, 2, 4, 2, 3),
             nn.Tanh(),
             ]
        self.Sequential = nn.Sequential(*m)
        for m in self.modules():
            if isinstance(m, (nn.Conv2d, nn.ConvTranspose2d)):
                nn.init.kaiming_normal_(m.weight, mode='fan_out', nonlinearity='relu')
                if m.bias is not None:
                    nn.init.constant_(m.bias, 0)

    def forward(self, x):
        x = torch.ones_like(x) - x
        y = self.Sequential.forward(x)
        y = torch.ones_like(y) * 0.5 - y * 0.55
        return y

class Upscaler:
    def __init__(self, model_path, tile_size=256, vis_model=False):
        self.vis_model = vis_model

        map_location = torch.device(device)

        self.model_select = UpSelect_7_V2().to(device)
        self.model_select.load_state_dict(torch.load(os.path.join(model_path, "select.pth"), map_location))
        self.model_select.eval()

        self.model_image = UpConv_7().to(device)
        self.model_image.load_state_dict(torch.load(os.path.join(model_path, "image.pth"), map_location))
        self.model_image.eval()

        self.model_kanji = UpConv_7_KanjiV2().to(device)
        self.model_kanji.load_state_dict(torch.load(os.path.join(model_path, "kanji.pth"), map_location))
        self.model_kanji.eval()

        alignment = 32
        max_padding = max(
            self.model_select.padding,
            self.model_image.padding,
            self.model_kanji.padding)

        self.padding = align_up(max_padding, alignment)
        self.alignment = alignment
        self.tile_size = align_up(tile_size, alignment)

    def upscale_region(self, x):
        normalization = 1.0 / 255.0

        x = x.to(torch.float32) * normalization
        x = x.to(device)
        x = torch.unsqueeze(x, 0)

        Xa = self.model_image(x)
        Xb = self.model_kanji(x)
        pred = self.model_select(x)

        xh, xw = x.shape[2], x.shape[3]
        Xs = TVF.resize(x, (xh, xw), TVT.InterpolationMode.BICUBIC, antialias=True)

        h = min(Xa.shape[2], Xb.shape[2], pred.shape[2])
        w = min(Xa.shape[3], Xb.shape[3], pred.shape[3])

        Xa = TVF.center_crop(Xa, (h, w))
        Xb = TVF.center_crop(Xb, (h, w))
        Xs = TVF.center_crop(Xs, (h, w))
        pred = TVF.center_crop(pred, (h, w))

        pred = torch.clamp(pred, 0, 1)
        pred_t = pred[:, 0:1, :, :]
        pred_s = pred[:, 1:2, :, :]

        Xp = Xa * (1.0 - pred_t) + Xb * pred_t
        Xp = Xs * (1.0 - pred_s) + Xp * pred_s

        pred = torch.squeeze(pred, 0)
        Xp = torch.squeeze(Xp, 0)
        Xp = torch.clamp(Xp, 0, 1)

        return Xp, pred

    def upscale(self, image):
        
        with torch.inference_mode():
            image = image.convert("L")
            im_width, im_height = image.size
            image_t = TVF.pil_to_tensor(image)

            pad, align, tile_size = self.padding, self.alignment, self.tile_size

            pad_x = pad + align_up(im_width, align) - im_width
            pad_y = pad + align_up(im_height, align) - im_height

            image_pad = TVF.pad(image_t, (pad, pad, pad_x, pad_y))
            _, pad_height, pad_width = image_pad.shape

            result_pad = torch.zeros(1, pad_height * 2, pad_width * 2)
            if self.vis_model:
                pred_pad = torch.zeros(2, pad_height * 2, pad_width * 2) 

            advance = self.tile_size - pad
            assert advance > 0
            for start_y in range(0, pad_height, advance):
                for start_x in range(0, pad_width, advance):
                    end_y = min(start_y + tile_size, pad_height)
                    end_x = min(start_x + tile_size, pad_width)

                    region = image_pad[:, start_y:end_y, start_x:end_x]
                    up_region, pred_region = self.upscale_region(region)

                    _, lo_h, lo_w = region.shape
                    _, hi_h, hi_w = up_region.shape

                    off_y = (lo_h*2 - hi_h) // 2
                    off_x = (lo_w*2 - hi_w) // 2

                    dst_y = start_y * 2 + off_y
                    dst_x = start_x * 2 + off_x
                    result_pad[:, dst_y:dst_y+hi_h, dst_x:dst_x+hi_w] = up_region
                    if self.vis_model:
                        pred_pad[:, dst_y:dst_y+hi_h, dst_x:dst_x+hi_w] = pred_region

            result = result_pad[:, pad*2:-pad_y*2, pad*2:-pad_x*2]

            if self.vis_model:
                pred = pred_pad[:, pad*2:-pad_y*2, pad*2:-pad_x*2]
                pred_t = pred[0:1, :, :]
                pred_s = pred[1:2, :, :]
                im_result = TVF.to_pil_image(result, mode="L")
                result_c = im_result.convert("RGB")

                im_pred_t = TVF.to_pil_image(pred_t, mode="L")
                im_pred_s = TVF.to_pil_image(pred_s, mode="L")

                image_gradient = gradient("#a50e25", "#f6d7df")
                text_gradient = gradient("#0f41d0", "#d4e6ff")

                image_c = result_c.point(image_gradient)
                text_c = result_c.point(text_gradient)

                model_c = Image.composite(text_c, image_c, im_pred_t)
                return Image.composite(model_c, result_c, im_pred_s)
            else:
                im = TVF.to_pil_image(result, mode="L")
            return im

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Upscale Manga pages")
    parser.add_argument("sources", nargs="+", metavar="source-path/", help="Source paths for the images")
    parser.add_argument("-o", required=True, metavar="output-path/", help="Output path for the images")
    parser.add_argument("--model", default="model", help="Path to locate the models from")
    parser.add_argument("--downscale", type=float, help="Reduce the final resolution")
    parser.add_argument("--no-progress", action="store_true", help="Don't report progress percentage")
    parser.add_argument("--tile-size", default=256, type=int, help="Size of the tiles used to process")
    parser.add_argument("--vis-model", action="store_true", help="Visualize which model was used per-pixel")
    args = parser.parse_args()

    print(f"Using {device} device")
    print("Initializing models...")
    upscaler = Upscaler(args.model, args.tile_size, args.vis_model)

    os.makedirs(args.o, exist_ok=True)

    files = []

    for src in args.sources:
        if os.path.isdir(src):
            files += [os.path.join(src, p) for p in os.listdir(src)]
        else:
            files.append(src)

    for n, path in enumerate(files):
        base, ext = os.path.splitext(path)
        base = os.path.basename(base)
        if ext.lower() in (".jpg", ".jpeg", ".png"):
            prog = ""
            if not args.no_progress:
                p = ((n+1) / len(files) * 100)
                prog = f" <{p:.1f}%>"
            print(f"[{n+1}/{len(files)}]{prog} {path}")
            with Image.open(path) as im:
                im2 = upscaler.upscale(im)
                
                if args.downscale:
                    w, h = im2.size
                    im_old = im2
                    im2 = im2.resize((int(w * args.downscale), int(h * args.downscale)), Image.BICUBIC)
                    im_old.close()
                
                dst_path = os.path.join(args.o, f"{base}.png")
                im2.save(dst_path)
                im2.close()
